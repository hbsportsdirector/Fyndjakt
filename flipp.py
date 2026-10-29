"""Flipp-spåret: betyget sätts på pris i stället för smak.

För spår med `flipp: true` används Claude bara för att identifiera föremålet (fabrik/formgivare/serie),
föreslå en sökfras för prisjämförelse och varna för nyproduktion, kopior och skador. Sedan hämtas vad
jämförbara föremål klubbats för på Auctionet, och koden räknar på upplägget "köp var som helst, sälj via ett
auktionshus på Auctionet":

    inköp = pris × (1 + köparprovision för källan) + frakt för källan
    netto = typiskt slutpris (median) × (1 − säljarprovision) − avgift per föremål
    kvot  = inköp / netto:  ≤ 0,35 → 10    ≤ 0,50 → 8    ≤ 0,70 → 6    annars 0

Blir vinsten (netto − inköp) under MIN_VINST ger det 0 – då är det inte värt besväret.
Färre än 5 jämförelser (eller ingen median) ger 0. Nyproduktion/replika och föremål utanför keramik, glas och
design får 0; övriga varningar (kopia, skada) sänker betyget med 3. Jämförelsen görs på samma föremålstyp
("Picknick underlägg", inte "Picknick"); finns för få sålda av typen används en typlös jämförelse × 0,4. Auktioner med mer än två dygn kvar betygsätts inte än (0) – ett bud på
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
NYPRODUKTION = "nyproduktion"
TYPLOS_ANDEL = 0.4       # typlös jämförelse (för få sålda av samma typ): median × 0,4
MIN_TYPADE = 3           # färre sålda av samma typ → typlös jämförelse
BILDER = 3               # bilder per annons – stämplar och baksidor avgör äktheten
BILD_STORLEK = 640       # pixlar på längsta sidan (större än smakbedömningens, för att kunna läsa stämplar)
# Små föremål jämförs aldrig mot stora – en servis eller karott med underlägg i titeln säger inget om underlägget.
SMA_TYPER = ("underlägg", "äggkopp", "mugg", "assiett", "tefat")
STORA_TYPER = ("karott", "kanna", "kannor", "servis")
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
- ange föremålstypen i ett ord, i singular (t.ex. "underlägg", "äggkopp", "mugg", "assiett", "tefat", "tekanna",
  "karott", "vas", "figurin").
- ge en sökfras (2–5 ord, svenska) som hittar JÄMFÖRBARA SÅLDA föremål på Auctionet: formgivare eller fabrik
  + serie + föremålstypen, t.ex. "Picknick underlägg", "Berså tekanna", "Lisa Larson lejon", "Kåge Argenta vas".
  Föremålstypen MÅSTE ingå – "Picknick" ensamt jämför ett underlägg med karotter och serviser.
  Ta inte med ord som sällan står i auktionstitlar (färger, mått, "fin", "vintage").

Avgör om föremålet är ORIGINAL (produktionsperiod) eller NYPRODUKTION/REPLIKA. Kännetecken på nyproduktion: Rörstrand krönt R-logo (2000+) i stället för tre kronor; "Made in Sri Lanka/Thailand/Indonesia/Portugal"; Picknick i vit, blank, tunn benporslin med skarpt tryck och runda muggar/underlägg med kork; Berså med ankarstämpel utan bladlogotyp eller "Gustafsberg"-stavning tryckt; Paratiisi med runda tallrikar; Lisa Larson "K-Studion" eller japansk märkning utan krackelering; Mon Amie 0,33 l-mugg; Muminmugg med "By Arabia" eller Made in Thailand; glas/porslin med streckkodsetikett eller nypris. Titlar med "ny", "nytt", "oanvänd", "i kartong", "nyproduktion", "nyutgåva", "modern", "2000-tal", "2010-tal" talar för nyproduktion. Svara med "varning" = "nyproduktion" när något av detta syns, och "akthet_sakerhet" 0–1.

Titta på ALLA bilderna (stämpel, baksida, etiketter) innan du avgör äktheten.
- "varning": "nyproduktion" enligt ovan; annars kort om det är en kopia/reproduktion, eller om skada syns eller
  nämns (nagg, spricka, lagning, slitet dekor).
  Kan du bara se fabriken men inte serie, modell eller formgivare, skriv "oidentifierad serie" – då blir
  jämförelsen för allmän. Annars tom sträng.
- sätt "utanfor" till true om föremålet INTE är keramik, glas eller formgivet konsthantverk (t.ex. textil, tyg,
  kläder, möbler, smycken, böcker, bilder, licensprodukter som påsar och muggunderlägg i papp), annars false.

Svara ENBART med en JSON-lista, en post per annons, utan annan text:
[{"nr": 1, "jamforsok": "<sökfras med föremålstyp>", "typ": "<föremålstyp>", "identifierat": "<fabrik/formgivare/serie>", "varning": "<nyproduktion, kopia, skada, oidentifierad serie eller tom sträng>", "akthet_sakerhet": <0–1>, "utanfor": false}, …]"""


# ── Betyget ────────────────────────────────────────────────────────

def nyproduktion(varning: str) -> bool:
    v = (varning or "").lower()
    return NYPRODUKTION in v or "replika" in v


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
    if (varning or "").strip().lower().startswith(UTANFOR.lower()) or nyproduktion(varning):
        return 0, kvot  # sållas bort – nyproduktion och fel sortiment är aldrig fynd
    if vinst(pris, median, kalla) < MIN_VINST:
        return 0, kvot  # inte värt besväret
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
    utan_typ = " (jämförelse utan typ)" if jmf.get("sakerhet") == "låg" else ""
    text = (f"{pris_etikett(pris_text)} {_kr(pris)}, klubbas typiskt för {_kr(jmf['median'])} "
            f"({jmf['antal']} jämförelser){utan_typ}")
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
    if nyproduktion(varning):
        return 0, kvot, f"Nyproduktion – inget fynd. {text}"
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

_BILDER: dict[str, str | None] = {}


def bilder_for(a) -> list[str]:
    """Upp till BILDER olika bilder – samma bild i flera storlekar (Tradera: images/… och medium/…) räknas en gång."""
    ut, sedda = [], set()
    for u in a.bilder:
        namn = u.rsplit("/", 1)[-1].split("?")[0]
        if u and namn not in sedda:
            sedda.add(namn)
            ut.append(u)
    return ut[:BILDER]


def forbered_bilder(urls: list[str], tradar: int = 16) -> None:
    from concurrent.futures import ThreadPoolExecutor
    nya = [u for u in dict.fromkeys(urls) if u and u not in _BILDER]
    with ThreadPoolExecutor(max_workers=tradar) as pool:
        for u, b64 in zip(nya, pool.map(lambda u: bedomning._forminska(u, BILD_STORLEK), nya)):
            _BILDER[u] = b64


def bildblock(url: str) -> dict:
    if url not in _BILDER:
        _BILDER[url] = bedomning._forminska(url, BILD_STORLEK)
    if _BILDER[url]:
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _BILDER[url]}}
    return {"type": "image", "source": {"type": "url", "url": url}}


def forfragan(annonser: list, modell: str) -> dict:
    innehall = []
    for nr, a in enumerate(annonser, 1):
        bilder = bilder_for(a)
        innehall.append({"type": "text", "text": (
            f"Annons {nr} ({len(bilder)} bilder):\nTitel: {a.titel}\nPris: {a.pris_text}\n"
            f"Beskrivning: {a.beskrivning[:900]}")})
        innehall += [bildblock(u) for u in bilder]
    return {"model": modell, "max_tokens": 140 * len(annonser) + 50, "system": INSTRUKTION,
            "messages": [{"role": "user", "content": innehall}]}


def med_typ(fras: str, typ: str) -> str:
    """Sökfrasen med föremålstypen – lägg till typen om Claude glömt den."""
    fras, typ = fras.strip(), (typ or "").strip().lower()
    if typ and typ[:max(3, len(typ) - 2)] not in fras.lower():
        fras = f"{fras} {typ}"
    return fras[:60]


def utan_typ(fras: str, typ: str) -> str:
    """Sökfrasen utan föremålstypen (för den typlösa reservjämförelsen)."""
    typ = (typ or "").strip().lower()
    if not typ:
        return ""
    stam = typ[:max(3, len(typ) - 2)]
    return " ".join(o for o in fras.split() if stam not in o.lower())


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
            typ = str(d.get("typ") or "").strip().lower()[:30]
            try:
                sakerhet = max(0.0, min(1.0, float(d.get("akthet_sakerhet"))))
            except (TypeError, ValueError):
                sakerhet = None
            ut[nr] = {"jamforsok": med_typ(fras, typ), "typ": typ,
                      "identifierat": str(d.get("identifierat") or "").strip()[:120],
                      "varning": varning, "akthet_sakerhet": sakerhet}
    return ut


def identifiera(annonser: list, modell: str, klient, storlek: int = bedomning.GRUPPSTORLEK,
                max_vant: int = 40 * 60, intervall: int = 30) -> dict[str, dict]:
    """{annonsnyckel: identifiering}. Allt i en batch (halva priset); det som saknas försöks igen nästa körning."""
    if not annonser:
        return {}
    forbered_bilder([u for a in annonser for u in bilder_for(a)])
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


def jamfor_typat(fras: str, typ: str) -> dict | None:
    """Jämförelse på samma föremålstyp. Små föremål (underlägg, äggkoppar …) jämförs aldrig mot karotter, kannor
    och serviser. Färre än MIN_TYPADE sålda av typen: typlös sökning, median × 0,4 och sakerhet "låg"."""
    liten = any(t[:max(3, len(t) - 2)] in (typ or "") for t in SMA_TYPER)
    uteslut = STORA_TYPER if liten else ()
    res = prisjamforelse.jamfor(fras, uteslut)
    if res and res["antal"] >= MIN_TYPADE:
        return {**res, "sakerhet": ""}
    typlos = utan_typ(fras, typ)
    if not typlos or typlos.lower() == fras.lower():
        return res and {**res, "sakerhet": ""}
    bred = prisjamforelse.jamfor(typlos, uteslut)
    if not bred:
        return res and {**res, "sakerhet": ""}
    return {**bred, **{k: round(bred[k] * TYPLOS_ANDEL) for k in ("median", "lag", "hog")}, "sakerhet": "låg"}


def jamfor_alla(fraser: list[tuple[str, str]], tradar: int = 4) -> dict[tuple, dict | None]:
    """{(fras gemener, typ): jämförelse}. Fraser där hämtningen misslyckades saknas – de försöks igen nästa natt."""
    from concurrent.futures import ThreadPoolExecutor
    unika = list(dict.fromkeys((f.lower(), t) for f, t in fraser if f))

    def en(nyckel):
        try:
            return nyckel, jamfor_typat(*nyckel), True
        except Exception as e:
            print(f"  Prisjämförelse misslyckades för '{nyckel[0]}': {e}")
            return nyckel, None, False
    with ThreadPoolExecutor(tradar) as pool:
        return {k: res for k, res, ok in pool.map(en, unika) if ok}


def spara(db, a, info: dict, jmf: dict | None) -> int:
    """Sparar annonsen med maskinbetyg, prisjämförelse och flippfälten. Returnerar betyget."""
    b, kvot, text = bedom_post(a.pris, a.pris_text, a.slutar_ts, jmf, info.get("varning", ""), kalla=a.kalla)
    a.jamforsok = info["jamforsok"]
    db.spara(a, b, text, b >= 10)
    db.spara_jamforelse(a.nyckel, info["jamforsok"], jmf)
    median = (jmf or {}).get("median")
    db.spara_flipp(a.nyckel, kvot, kop_max(median, a.kalla), info.get("identifierat", ""),
                   info.get("varning", ""), (jmf or {}).get("sakerhet", ""), info.get("akthet_sakerhet"),
                   vinst(a.pris, median, a.kalla))
    return b


def bedom(kandidater: list, db, cfg: dict, klient, berika=None, statistik: dict | None = None) -> list[tuple]:
    """Identifierar, prisjämför och betygsätter flipp-kandidaterna. Returnerar [(betyg, annons, median)] för 10:or.
    berika(annons) hämtar annonssidan (fler bilder och längre beskrivning) för de valda."""
    if not kandidater:
        return []
    kandidater = valj(kandidater, cfg)
    if berika:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(6) as pool:
            list(pool.map(berika, kandidater))
    ident = {}
    per_spar: dict[str, list] = {}
    for a in kandidater:
        per_spar.setdefault(a.spar, []).append(a)
    for sid, lista in per_spar.items():  # spårets egen modell (flipp: Sonnet), annars den vanliga
        ident.update(identifiera(lista, cfg["spar"][sid].get("modell") or cfg["modell"], klient,
                                 cfg.get("gruppstorlek", bedomning.GRUPPSTORLEK)))
    jmf = jamfor_alla([(i["jamforsok"], i.get("typ", "")) for i in ident.values()])
    tio, sparade, nypr, utan_typ_ = [], 0, 0, 0
    for a in kandidater:
        info = ident.get(a.nyckel)
        nyckel = info and (info["jamforsok"].lower(), info.get("typ", ""))
        if not info or nyckel not in jmf:
            continue  # sparas inte – försöker igen nästa natt
        res = jmf[nyckel]
        b = spara(db, a, info, res)
        sparade += 1
        nypr += nyproduktion(info.get("varning", ""))
        utan_typ_ += bool(res and res.get("sakerhet") == "låg")
        print(f"  {b:2}/10 [flipp] {a.titel[:55]} | {a.pris_text} | {info['jamforsok']} | median "
              f"{(res or {}).get('median')}{' (utan typ)' if res and res.get('sakerhet') else ''}"
              f"{' | NYPRODUKTION' if nyproduktion(info.get('varning', '')) else ''}")
        if b >= 10:
            tio.append((b, a, res["median"]))
    print(f"Flipp: {sparade} bedömda, {nypr} nyproduktion, {len(tio)} med betyg 10.")
    if statistik is not None:
        statistik.update({"bedömda": sparade, "nyproduktion": nypr, "jämförelse utan typ": utan_typ_})
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
            f"SELECT nyckel, pris, betyg, motivering, kop_max, vinst, jmf_median, jmf_antal, jmf_sakerhet, varning "
            f"FROM sedda WHERE nyckel IN ({platser}) AND jmf_tid IS NOT NULL AND betyg >= 0", list(flipp)).fetchall():
        a = flipp[r["nyckel"]]
        jmf = {"median": r["jmf_median"], "antal": r["jmf_antal"], "sakerhet": r["jmf_sakerhet"] or ""}
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
