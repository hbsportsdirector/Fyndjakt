"""Flipp-spåret: betyget sätts på pris i stället för smak.

För spår med `flipp: true` används Claude bara för att identifiera föremålet (fabrik/formgivare/serie),
föreslå en sökfras för prisjämförelse och varna för nyproduktion, kopior och skador. Sedan hämtas vad
jämförbara föremål klubbats för på Auctionet, och koden räknar på upplägget "köp var som helst, sälj via ett
auktionshus på Auctionet":

    inköp = pris × (1 + köparprovision för källan) + frakt för källan
    netto = typiskt slutpris (median) × (1 − säljarprovision) − avgift per föremål
    kvot  = inköp / netto:  ≤ 0,35 → 10    ≤ 0,50 → 8    ≤ 0,70 → 6    annars 0

Blir vinsten (netto − inköp) under MIN_VINST ger det 0 – då är det inte värt besväret.
Färre än 5 jämförelser (eller ingen median) ger 0. En varning från Claude sänker betyget med 3, och föremål
utanför keramik, glas och design får 0. Auktioner med mer än två dygn kvar betygsätts inte än (0) – ett bud på
1 kr fem dagar före slutet säger inget om slutpriset. De räknas om varje natt tills de är inom två dygn.
"""
import json
import re
import time

import bedomning
import prisjamforelse

MIN_JAMFORELSER = 5
TIDIG = 2 * 86400        # auktioner med mer kvar än så betygsätts inte än
UTANFOR = "Utanför keramik, glas och design"
VARNINGSAVDRAG = 3
STEG = [(0.35, 10), (0.50, 8), (0.70, 6)]   # kvot = inköp / netto

# Kalkylen: sälj via ett auktionshus på Auctionet. Uppskattningar – provisioner och avgifter varierar mellan husen.
SALJ_PROVISION = 0.20    # säljarprovision på klubbat pris
SALJ_AVGIFT = 100        # avgifter per föremål (foto, hantering)
KOP_PROVISION = {"auctionet": 0.25, "bukowskis": 0.25}   # köparprovision på budet
KOP_FRAKT = {"tradera": 80}                             # frakt när köpet skickas (övriga hämtas)
MIN_VINST = 300          # kr kvar efter alla kostnader – annars inte värt besväret
KOP_MAX_KVOT = 0.50      # köp max = högsta pris där inköpet är högst halva nettot (betyg 8) och vinsten räcker

INSTRUKTION = """Du är expert på nordisk keramik, glas och design och hjälper en uppköpare som köper på auktion
och säljer vidare. Du bedömer INTE om föremålen är snygga – priset räknas ut separat mot vad liknande
föremål har klubbats för.

Du får flera annonser, numrerade "Annons 1", "Annons 2" … – varje annons med sin text och sin bild direkt efter.
Blanda inte ihop annonserna – bilden hör till annonsen som står närmast före den. För VARJE annons:
- identifiera föremålet: fabrik, formgivare och serie/modell (t.ex. "Gustavsberg, Lisa Larson, Stora Zoo").
- ge en sökfras (2–5 ord, svenska) som hittar JÄMFÖRBARA SÅLDA föremål på Auctionet: formgivare eller fabrik
  + serie + föremålstyp, t.ex. "Berså tekanna", "Lisa Larson lejon", "Kåge Argenta vas", "Arabia Paratiisi tallrik".
  Ta inte med ord som sällan står i auktionstitlar (färger, mått, "fin", "vintage").
- varna kort om det är nyproduktion (t.ex. nytillverkade Berså/Spisa Ribb/Lisa Larson efter 1990, K-Studion),
  en kopia/reproduktion, eller om skada syns eller nämns (nagg, spricka, lagning, slitet dekor).
  Kan du bara se fabriken men inte serie, modell eller formgivare, skriv "oidentifierad serie" – då blir
  jämförelsen för allmän. Annars tom sträng.
- sätt "utanfor" till true om föremålet INTE är keramik, glas eller formgivet konsthantverk (t.ex. textil, tyg,
  kläder, möbler, smycken, böcker, bilder, licensprodukter som påsar och muggunderlägg i papp), annars false.

Svara ENBART med en JSON-lista, en post per annons, utan annan text:
[{"nr": 1, "jamforsok": "<sökfras>", "identifierat": "<fabrik/formgivare/serie>", "varning": "<nyproduktion, kopia, skada, oidentifierad serie eller tom sträng>", "utanfor": false}, …]"""


# ── Betyget ────────────────────────────────────────────────────────

def inkop(pris: int, kalla: str = "") -> float:
    """Vad köpet kostar: priset plus köparprovision och frakt för källan."""
    return pris * (1 + KOP_PROVISION.get(kalla, 0)) + KOP_FRAKT.get(kalla, 0)


def netto(median: int) -> float:
    """Vad man får ut när föremålet klubbas för medianen, efter säljarprovision och avgifter."""
    return median * (1 - SALJ_PROVISION) - SALJ_AVGIFT


def vinst(pris: int | None, median: int | None, kalla: str = "") -> int | None:
    return int(round(netto(median) - inkop(pris, kalla))) if pris and median else None


def betyg(pris: int | None, median: int | None, antal: int | None, varning: str = "",
          kalla: str = "") -> tuple[int, float | None]:
    """(betyg 0–10, kvot = inköp / netto). Kvoten är None när den inte går att räkna ut."""
    if not median or (antal or 0) < MIN_JAMFORELSER or not pris or netto(median) <= 0:
        return 0, None
    kvot = inkop(pris, kalla) / netto(median)
    b = next((b for grans, b in STEG if kvot <= grans), 0)
    if (varning or "").strip().lower().startswith(UTANFOR.lower()) or vinst(pris, median, kalla) < MIN_VINST:
        return 0, kvot
    if b and (varning or "").strip():
        b = max(0, b - VARNINGSAVDRAG)
    return b, kvot


def kop_max(median: int | None, kalla: str = "") -> int | None:
    """Högsta pris (bud/utrop) som ger kvot ≤ KOP_MAX_KVOT och minst MIN_VINST. None = lönar sig aldrig."""
    if not median:
        return None
    tak = min(netto(median) * KOP_MAX_KVOT, netto(median) - MIN_VINST) - KOP_FRAKT.get(kalla, 0)
    pris = int(tak / (1 + KOP_PROVISION.get(kalla, 0)))
    return pris if pris > 0 else None


def pris_etikett(pris_text: str) -> str:
    """"Bud", "Utrop" eller "Köp nu" – det aktuella priset är högsta budet om det finns, annars utropet."""
    t = (pris_text or "").strip().lower()
    return "Bud" if t.startswith(("bud", "ledande bud", "högsta bud")) else "Köp nu" if t.startswith("köp nu") else "Utrop"


def auktion(pris_text: str, slutar_ts: int | None) -> bool:
    """Pågående auktion (priset kan stiga) – inte köp nu eller fast pris."""
    return bool(slutar_ts) and pris_etikett(pris_text) != "Köp nu"


def for_tidig(pris_text: str, slutar_ts: int | None, nu: float | None = None) -> bool:
    return auktion(pris_text, slutar_ts) and slutar_ts - (nu or time.time()) > TIDIG


def _kr(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " kr"


def motivering(pris: int | None, pris_text: str, jmf: dict | None, varning: str = "", kalla: str = "") -> str:
    """Maskinbyggd: "Utrop 150 kr, klubbas typiskt för 1 000 kr (12 jämförelser) – vinst ca 510 kr på Auctionet,
    köp max 280 kr." """
    jmf = jmf or {}
    if not jmf.get("median") or (jmf.get("antal") or 0) < MIN_JAMFORELSER:
        return f"För få jämförelser ({jmf.get('antal') or 0} sålda)."
    if not pris:
        return "Pris saknas – går inte att jämföra."
    text = f"{pris_etikett(pris_text)} {_kr(pris)}, klubbas typiskt för {_kr(jmf['median'])} ({jmf['antal']} jämförelser)"
    km = kop_max(jmf["median"], kalla)
    if km:
        text += f" – vinst ca {_kr(vinst(pris, jmf['median'], kalla))} på Auctionet, köp max {_kr(km)}."
    else:
        text += " – för lågt värde för att löna sig att sälja på Auctionet."
    if (varning or "").strip():
        text += f" Varning: {varning.strip()}."
    return text


def bedom_post(pris: int | None, pris_text: str, slutar_ts: int | None, jmf: dict | None, varning: str = "",
               nu: float | None = None, kalla: str = "") -> tuple[int, float | None, str]:
    """(betyg, kvot, motivering) för en annons – samma regler när den bedöms första gången och när den räknas om."""
    jmf = jmf or {}
    b, kvot = betyg(pris, jmf.get("median"), jmf.get("antal"), varning, kalla)
    text = motivering(pris, pris_text, jmf, varning, kalla)
    if (varning or "").strip().lower().startswith(UTANFOR.lower()):
        return 0, kvot, f"{UTANFOR}."
    if b and for_tidig(pris_text, slutar_ts, nu):
        dagar = round((slutar_ts - (nu or time.time())) / 86400)
        return 0, kvot, f"Slutar om {dagar} dagar – betygsätts när under två dygn återstår. {text}"
    return b, kvot, text


def notistext(a, median: int) -> str:
    """Egen Telegram-notis för flipp-fynd med betyg 10."""
    import html
    return (f"🔎 Flipp: {html.escape(a.titel[:200])} – {pris_etikett(a.pris_text).lower()} {_kr(a.pris)}, "
            f"klubbas typiskt {_kr(median)}, vinst ca {_kr(vinst(a.pris, median, a.kalla))}. {html.escape(a.url)}")


# ── Identifiering med Claude ───────────────────────────────────────

def forfragan(annonser: list, modell: str) -> dict:
    innehall = []
    for nr, a in enumerate(annonser, 1):
        innehall.append({"type": "text", "text": (
            f"Annons {nr}:\nTitel: {a.titel}\nPris: {a.pris_text}\nBeskrivning: {a.beskrivning[:700]}")})
        innehall += [bedomning.bildblock(u) for u in a.bilder[:bedomning.BILDER]]
    return {"model": modell, "max_tokens": 90 * len(annonser) + 50, "system": INSTRUKTION,
            "messages": [{"role": "user", "content": innehall}]}


def tolka(text: str, antal: int) -> dict[int, dict]:
    """{nr: {"jamforsok", "identifierat", "varning"}} – trasiga eller saknade poster utelämnas."""
    poster = []
    match = re.search(r"\[.*\]", text, re.S)
    if match:
        try:
            poster = json.loads(match.group(0))
        except ValueError:
            poster = []
    if not poster:  # avklippt svar – rädda de poster som är hela
        for m in re.finditer(r"\{[^{}]*\}", text):
            try:
                poster.append(json.loads(m.group(0)))
            except ValueError:
                pass
    ut = {}
    for d in poster:
        try:
            nr = int(d.get("nr"))
        except (TypeError, ValueError, AttributeError):
            continue
        fras = str(d.get("jamforsok") or "").strip()
        if 1 <= nr <= antal and fras:
            varning = str(d.get("varning") or "").strip()[:120]
            if d.get("utanfor") is True or str(d.get("utanfor")).lower() == "true":
                varning = UTANFOR  # sparas som varning så att omräkningarna också ger 0
            ut[nr] = {"jamforsok": fras[:60], "identifierat": str(d.get("identifierat") or "").strip()[:120],
                      "varning": varning}
    return ut


def identifiera(annonser: list, modell: str, klient, storlek: int = bedomning.GRUPPSTORLEK,
                max_vant: int = 40 * 60, intervall: int = 30) -> dict[str, dict]:
    """{annonsnyckel: identifiering}. Allt i en batch (halva priset); det som saknas försöks igen nästa körning."""
    if not annonser:
        return {}
    bedomning.forbered_bilder([u for a in annonser for u in a.bilder[:bedomning.BILDER]])
    grupper = {f"f{i // storlek}": annonser[i:i + storlek] for i in range(0, len(annonser), storlek)}
    batch = klient.messages.batches.create(
        requests=[{"custom_id": cid, "params": forfragan(bit, modell)} for cid, bit in grupper.items()])
    print(f"  Flipp: {len(annonser)} annonser i {len(grupper)} grupper skickade för identifiering …")
    start = time.time()
    while klient.messages.batches.retrieve(batch.id).processing_status != "ended":
        if time.time() - start > max_vant:
            print("  Flipp-identifieringen tog för lång tid – använder det som hann bli klart.")
            if not bedomning._avsluta_batch(klient, batch.id, intervall):
                return {}
            break
        time.sleep(intervall)
    ut = {}
    for rad in klient.messages.batches.results(batch.id):
        if rad.result.type == "errored" and "credit balance" in str(getattr(rad.result, "error", "")).lower():
            raise bedomning.SlutPaKrediter(str(rad.result.error))
        if rad.result.type != "succeeded":
            continue
        bit = grupper[rad.custom_id]
        bedomning.registrera("Flipp-identifiering", rad.result.message, batch=True)
        for nr, info in tolka(bedomning._text(rad.result.message), len(bit)).items():
            ut[bit[nr - 1].nyckel] = info
    print(f"  Flipp-identifiering klar: {len(ut)} av {len(annonser)}.")
    return ut


# ── Urval, bedömning och prisuppdatering ───────────────────────────

def valj(kandidater: list, cfg: dict, nu: float | None = None) -> list:
    """Högst `granska_max_per_sokord` per sökord och `max_bedomningar` per flipp-spår och natt – det som slutar
    först går först (där ligger priset närmast slutpriset). Auktioner med mer än två dygn kvar väntar.
    Det som inte väljs är osparat och kommer med nästa natt."""
    max_per = cfg.get("granska_max_per_sokord", 25)
    per_sokord: dict[tuple, int] = {}
    per_spar: dict[str, int] = {}
    ut = []
    kandidater = [a for a in kandidater if not for_tidig(a.pris_text, a.slutar_ts, nu)]
    for a in sorted(kandidater, key=lambda a: a.slutar_ts or 9e12):
        tak = cfg["spar"][a.spar].get("max_bedomningar", 300)
        k = (a.spar, a.sokord)
        if per_sokord.get(k, 0) >= max_per or per_spar.get(a.spar, 0) >= tak:
            continue
        per_sokord[k] = per_sokord.get(k, 0) + 1
        per_spar[a.spar] = per_spar.get(a.spar, 0) + 1
        ut.append(a)
    if len(ut) < len(kandidater):
        print(f"Flipp: bedömer {len(ut)} av {len(kandidater)} – resten tas nästa körning.")
    return ut


def jamfor_alla(fraser: list[str], tradar: int = 4) -> dict[str, dict | None]:
    """{fras (gemener): jämförelse}. Fraser där hämtningen misslyckades saknas – de försöks igen nästa natt."""
    from concurrent.futures import ThreadPoolExecutor
    unika = list(dict.fromkeys(f.lower() for f in fraser if f))

    def en(fras):
        try:
            return fras, prisjamforelse.jamfor(fras), True
        except Exception as e:
            print(f"  Prisjämförelse misslyckades för '{fras}': {e}")
            return fras, None, False
    with ThreadPoolExecutor(tradar) as pool:
        return {f: res for f, res, ok in pool.map(en, unika) if ok}


def spara(db, a, info: dict, jmf: dict | None) -> int:
    """Sparar annonsen med maskinbetyg, prisjämförelse och flippfälten. Returnerar betyget."""
    b, kvot, text = bedom_post(a.pris, a.pris_text, a.slutar_ts, jmf, info.get("varning", ""), kalla=a.kalla)
    a.jamforsok = info["jamforsok"]
    db.spara(a, b, text, b >= 10)
    db.spara_jamforelse(a.nyckel, info["jamforsok"], jmf)
    median = (jmf or {}).get("median")
    db.spara_flipp(a.nyckel, kvot, kop_max(median, a.kalla), info.get("identifierat", ""),
                   info.get("varning", ""), vinst(a.pris, median, a.kalla))
    return b


def bedom(kandidater: list, db, cfg: dict, klient) -> list[tuple]:
    """Identifierar, prisjämför och betygsätter flipp-kandidaterna. Returnerar [(betyg, annons, median)] för 10:or."""
    if not kandidater:
        return []
    kandidater = valj(kandidater, cfg)
    ident = identifiera(kandidater, cfg["modell"], klient, cfg.get("gruppstorlek", bedomning.GRUPPSTORLEK))
    jmf = jamfor_alla([i["jamforsok"] for i in ident.values()])
    tio, sparade = [], 0
    for a in kandidater:
        info = ident.get(a.nyckel)
        if not info or info["jamforsok"].lower() not in jmf:
            continue  # sparas inte – försöker igen nästa natt
        res = jmf[info["jamforsok"].lower()]
        b = spara(db, a, info, res)
        sparade += 1
        print(f"  {b:2}/10 [flipp] {a.titel[:55]} | {a.pris_text} | median {(res or {}).get('median')}")
        if b >= 10:
            tio.append((b, a, res["median"]))
    print(f"Flipp: {sparade} bedömda, {len(tio)} med betyg 10.")
    return tio


def uppdatera_priser(annonser: list, db, cfg: dict) -> int:
    """Bud stiger och auktioner närmar sig slutet: aktiva flipp-annonser som redan bedömts räknas om med nattens
    pris och tid kvar (utan nytt Claude-anrop). Ändras kalkylen räknas allt om nästa natt."""
    flipp = {a.nyckel: a for a in annonser if cfg["spar"].get(a.spar, {}).get("flipp") and a.pris}
    if not flipp:
        return 0
    n = 0
    platser = ",".join("?" * len(flipp))
    for r in db.con.execute(
            f"SELECT nyckel, pris, betyg, motivering, kop_max, vinst, jmf_median, jmf_antal, varning FROM sedda "
            f"WHERE nyckel IN ({platser}) AND jmf_tid IS NOT NULL AND betyg >= 0", list(flipp)).fetchall():
        a = flipp[r["nyckel"]]
        jmf = {"median": r["jmf_median"], "antal": r["jmf_antal"]}
        b, kvot, text = bedom_post(a.pris, a.pris_text, a.slutar_ts, jmf, r["varning"] or "", kalla=a.kalla)
        km, v = kop_max(r["jmf_median"], a.kalla), vinst(a.pris, r["jmf_median"], a.kalla)
        if (a.pris, b, text, km, v) == (r["pris"], r["betyg"], r["motivering"], r["kop_max"], r["vinst"]):
            continue
        db.con.execute("UPDATE sedda SET pris=?, pris_text=?, betyg=?, motivering=?, kvot=?, kop_max=?, vinst=? "
                       "WHERE nyckel=?", (a.pris, a.pris_text, b, text, kvot, km, v, a.nyckel))
        n += 1
    db.con.commit()
    if n:
        print(f"Flipp: {n} priser uppdaterade.")
    return n
