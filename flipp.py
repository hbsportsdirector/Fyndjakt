"""Flipp-spåret: betyget sätts på pris i stället för smak.

För spår med `flipp: true` används Claude bara för att identifiera föremålet (fabrik/formgivare/serie),
föreslå en sökfras för prisjämförelse och varna för nyproduktion, kopior och skador. Sedan hämtas vad
jämförbara föremål klubbats för på Auctionet, och koden sätter betyget på kvoten
aktuellt pris / typiskt slutpris (median):

    kvot ≤ 0,35 → 10    ≤ 0,50 → 8    ≤ 0,70 → 6    annars 0

Färre än 3 jämförelser (eller ingen median) ger 0. En varning från Claude sänker betyget med 3.
"""
import json
import re
import time

import bedomning
import prisjamforelse

MIN_JAMFORELSER = 3
KOP_MAX_ANDEL = 0.33     # köp max = typiskt slutpris × 0,33
VARNINGSAVDRAG = 3
STEG = [(0.35, 10), (0.50, 8), (0.70, 6)]

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
  en kopia/reproduktion, eller om skada syns eller nämns (nagg, spricka, lagning, slitet dekor). Annars tom sträng.

Svara ENBART med en JSON-lista, en post per annons, utan annan text:
[{"nr": 1, "jamforsok": "<sökfras>", "identifierat": "<fabrik/formgivare/serie>", "varning": "<nyproduktion, kopia, skada eller tom sträng>"}, …]"""


# ── Betyget ────────────────────────────────────────────────────────

def betyg(pris: int | None, median: int | None, antal: int | None, varning: str = "") -> tuple[int, float | None]:
    """(betyg 0–10, kvot). Kvoten är None när den inte går att räkna ut."""
    if not median or (antal or 0) < MIN_JAMFORELSER or not pris:
        return 0, None
    kvot = pris / median
    b = next((b for grans, b in STEG if kvot <= grans), 0)
    if b and (varning or "").strip():
        b = max(0, b - VARNINGSAVDRAG)
    return b, kvot


def kop_max(median: int | None) -> int | None:
    # Avrundning uppåt vid ,5 (Pythons round avrundar 214,5 till 214): 650 kr → 215 kr.
    return int(median * KOP_MAX_ANDEL + 0.5) if median else None


def pris_etikett(pris_text: str) -> str:
    """"Bud", "Utrop" eller "Köp nu" – det aktuella priset är högsta budet om det finns, annars utropet."""
    t = (pris_text or "").strip().lower()
    return "Bud" if t.startswith("bud") else "Köp nu" if t.startswith("köp nu") else "Utrop"


def _kr(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " kr"


def motivering(pris: int | None, pris_text: str, jmf: dict | None, varning: str = "") -> str:
    """Maskinbyggd: "Utrop 150 kr, klubbas typiskt för 650 kr (12 jämförelser) – köp max 215 kr." """
    jmf = jmf or {}
    if not jmf.get("median") or (jmf.get("antal") or 0) < MIN_JAMFORELSER:
        return f"För få jämförelser ({jmf.get('antal') or 0} sålda)."
    if not pris:
        return "Pris saknas – går inte att jämföra."
    text = (f"{pris_etikett(pris_text)} {_kr(pris)}, klubbas typiskt för {_kr(jmf['median'])} "
            f"({jmf['antal']} jämförelser) – köp max {_kr(kop_max(jmf['median']))}.")
    if (varning or "").strip():
        text += f" Varning: {varning.strip()}."
    return text


def notistext(a, median: int) -> str:
    """Egen Telegram-notis för flipp-fynd med betyg 10."""
    import html
    return (f"🔎 Flipp: {html.escape(a.titel[:200])} – {pris_etikett(a.pris_text).lower()} {_kr(a.pris)}, "
            f"klubbas typiskt {_kr(median)}. {html.escape(a.url)}")


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
            ut[nr] = {"jamforsok": fras[:60], "identifierat": str(d.get("identifierat") or "").strip()[:120],
                      "varning": str(d.get("varning") or "").strip()[:120]}
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

def valj(kandidater: list, cfg: dict) -> list:
    """Högst `granska_max_per_sokord` per sökord och `max_bedomningar` per flipp-spår och natt – det som slutar
    först går först (där ligger priset närmast slutpriset). Resten är osparat och kommer med nästa natt."""
    max_per = cfg.get("granska_max_per_sokord", 25)
    per_sokord: dict[tuple, int] = {}
    per_spar: dict[str, int] = {}
    ut = []
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
    b, kvot = betyg(a.pris, (jmf or {}).get("median"), (jmf or {}).get("antal"), info.get("varning", ""))
    a.jamforsok = info["jamforsok"]
    db.spara(a, b, motivering(a.pris, a.pris_text, jmf, info.get("varning", "")), b >= 10)
    db.spara_jamforelse(a.nyckel, info["jamforsok"], jmf)
    db.spara_flipp(a.nyckel, kvot, kop_max((jmf or {}).get("median")), info.get("identifierat", ""),
                   info.get("varning", ""))
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
    """Bud stiger: aktiva flipp-annonser som redan bedömts räknas om med nattens pris (utan nytt Claude-anrop)."""
    flipp = {a.nyckel: a for a in annonser if cfg["spar"].get(a.spar, {}).get("flipp") and a.pris}
    if not flipp:
        return 0
    n = 0
    platser = ",".join("?" * len(flipp))
    for r in db.con.execute(
            f"SELECT nyckel, pris, betyg, jmf_median, jmf_antal, varning FROM sedda "
            f"WHERE nyckel IN ({platser}) AND jmf_tid IS NOT NULL AND betyg >= 0", list(flipp)).fetchall():
        a = flipp[r["nyckel"]]
        if a.pris == r["pris"]:
            continue
        jmf = {"median": r["jmf_median"], "antal": r["jmf_antal"]}
        b, kvot = betyg(a.pris, r["jmf_median"], r["jmf_antal"], r["varning"] or "")
        db.con.execute("UPDATE sedda SET pris=?, pris_text=?, betyg=?, motivering=?, kvot=? WHERE nyckel=?",
                       (a.pris, a.pris_text, b, motivering(a.pris, a.pris_text, jmf, r["varning"] or ""), kvot,
                        a.nyckel))
        n += 1
    db.con.commit()
    if n:
        print(f"Flipp: {n} priser uppdaterade.")
    return n
