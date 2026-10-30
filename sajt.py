"""Skriver fynddata till sajten (site/data/fynd.json). Själva sidan är en statisk app i site/ (index.html, app.js …)
som läser det inloggades fynd direkt från Supabase; filen här innehåller bara de publika spåren och när sidan senast
uppdaterades. Allt i site/ publiceras via GitHub Pages."""
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROT = Path(__file__).parent
UT = ROT / "site"

# Ort → region. Orter som saknas hamnar i "Övriga Sverige".
REGIONER = {
    "Stockholm": ["stockholm", "hägersten", "västberga", "ropsten", "norrtälje", "järna", "jarna", "södertälje", "nacka", "täby", "lidingö",
                  "sollentuna", "solna", "sundbyberg", "huddinge", "haninge", "värmdö", "sigtuna", "danderyd",
                  "upplands väsby", "vallentuna", "österåker", "tyresö", "botkyrka", "ekerö", "sickla", "bromma",
                  # fler postorter i Stockholms län (Tradera anger säljarens postort)
                  "stokholm", "järfälla", "jakobsberg", "kallhäll", "barkarby", "bandhagen", "västerhaninge", "årsta",
                  "åkersberga", "skogås", "tullinge", "spånga", "handen", "johanneshov", "skärholmen", "nykvarn",
                  "rosersberg", "märsta", "kista", "vällingby", "hässelby", "älvsjö", "farsta", "enskede", "enskededalen",
                  "skarpnäck", "hagersten", "hägerstensåsen", "aspudden", "liljeholmen", "midsommarkransen", "sköndal",
                  "bagarmossen", "tumba", "tungelsta", "jordbro", "brandbergen", "vendelsö", "trångsund", "huddinge",
                  "flemingsberg", "segeltorp", "fittja", "norsborg", "hallunda", "alby", "saltsjöbaden", "saltsjö-boo",
                  "saltsjö-duvnäs", "fisksätra", "gustavsberg", "hemmesta", "djurö", "stavsnäs", "ingarö", "vaxholm",
                  "resarö", "lidingo", "danderyd", "djursholm", "stocksund", "enebyberg", "täby kyrkby", "arninge",
                  "rönninge", "salem", "hölö", "mölnbo", "vagnhärad", "nynäshamn", "ösmo", "sorunda", "dalarö",
                  "upplands-bro", "kungsängen", "bro", "sollentuna", "rotebro", "häggvik", "edsbro", "rimbo",
                  "hallstavik", "älta", "orminge", "mörby", "rinkeby", "tensta", "hjulsta", "bergshamra", "frösunda",
                  "hammarby sjöstad", "södermalm", "kungsholmen", "östermalm", "vasastan", "gamla stan", "bålsta",
                  "tyresö strand", "bollmora", "lindalen", "sundbyberg", "duvbo", "hallonbergen", "ulriksdal"],
    "Uppsala och Mälardalen": ["uppsala", "västerås", "örebro", "eskilstuna", "katrineholm", "nyköping",
                               "enköping", "sala", "strängnäs", "köping", "arboga", "flen", "tierp", "östhammar"],
    "Östergötland, Småland och Blekinge": ["norrköping", "linköping", "motala", "söderköping", "kalmar", "växjö",
                                           "jönköping", "oskarshamn", "karlshamn", "karlskrona", "västervik",
                                           "vimmerby", "värnamo", "ljungby", "nässjö", "vadstena", "mjölby", "ronneby",
                                           "visby", "gotland"],
    "Skåne": ["helsingborg", "lund", "landskrona", "malmö", "malmo", "trelleborg", "ängelholm", "engelholm", "höör",
              "höganäs", "ystad", "kristianstad", "hässleholm", "eslöv", "simrishamn", "båstad", "skurup", "staffanstorp"],
    "Västsverige och Värmland": ["gothenburg", "göteborg", "borås", "vänersborg", "varberg", "halmstad", "laholm",
                                 "henån", "lysekil", "uddevalla", "trollhättan", "kungsbacka", "alingsås", "skövde",
                                 "lidköping", "mariestad", "falkenberg", "karlstad", "arvika", "kristinehamn",
                                 "strömstad", "kungälv", "stenungsund", "falköping"],
    "Norrland och Dalarna": ["umeå", "falun", "sundsvall", "hudiksvall", "sandviken", "mora", "örnsköldsvik", "gävle",
                             "luleå", "skellefteå", "östersund", "borlänge", "härnösand", "kiruna", "piteå",
                             "bollnäs", "söderhamn", "ludvika", "leksand", "rättvik", "avesta", "hedemora"],
}
_ORT_TILL_REGION = {ort: region for region, orter in REGIONER.items() for ort in orter}


def region_for(kalla: str, plats: str) -> tuple[str, str]:
    """Returnerar (ort, region) för en annons."""
    if kalla == "stadsmissionen":
        return "Stockholm", "Stockholm"
    if kalla == "myrorna":
        return "Stockholm (Ropsten)", "Stockholm"
    if kalla == "tradera" and not (plats or "").startswith("Tradera, "):
        return "", "Okänd ort"  # äldre annonser utan säljarens ort
    ort = (plats or "").split(", ")[-1].strip()
    if kalla == "bukowskis" and ort.lower() == "bukowskis":
        return "Stockholm", "Stockholm"  # äldre annonser utan läst placering; huvudlagret ligger i Stockholm
    if not ort:
        return "", "Övriga Sverige"
    region = _ORT_TILL_REGION.get(ort.lower())
    if region:
        return ort, region
    # Leta efter en känd ort någonstans i texten, t.ex. "Västberga Allé 3. 126 30 Hägersten -T13".
    text = (plats or "").lower()
    for kand in sorted(_ORT_TILL_REGION, key=len, reverse=True):
        if re.search(rf"(?<![a-zåäö]){re.escape(kand)}(?![a-zåäö])", text):
            return kand.title(), _ORT_TILL_REGION[kand]
    return ort, "Övriga Sverige"


FALT = ["nyckel", "titel", "url", "betyg", "motivering", "kalla", "kategori",
        "pris", "pris_text", "plats", "slutar", "slutar_ts", "bilder", "sedd", "spar",
        "jamforsok", "jmf_median", "jmf_lag", "jmf_hog", "jmf_antal", "sokord",
        "kvot", "kop_max", "identifierat", "varning", "jmf_sakerhet", "vinst", "styck"]


def _poster(db, cfg: dict, spar_ids: set[str] | None, rader: list[dict] | None = None) -> list[dict]:
    """Fynden som visas, bäst först. sajt_max_per_sokord (0 = ingen gräns) kan begränsa per sökord och spår."""
    min_betyg = cfg.get("sajt_min_betyg", 6)
    max_per = cfg.get("sajt_max_per_sokord") or 0
    per_sokord: dict[tuple, int] = {}
    poster = []
    for r in (rader if rader is not None else db.traffar(min_betyg)):  # redan sorterade bäst först
        if spar_ids is not None and r.get("spar") not in spar_ids:
            continue
        if str(r.get("motivering") or "").startswith(("Ej bildgranskad", "Sållad")):
            continue  # bara bildgranskade fynd visas
        ns = str((cfg.get("smak_nystart") or {}).get(r.get("spar")) or "")
        if ns and (r.get("betyg") or 0) < cfg.get("min_betyg", 8) and str(r.get("sedd") or "") < ns:
            continue  # "nästan"-fynd bedömda med en äldre smak visas inte
        nyckel = (r.get("spar"), r.get("sokord") or r.get("nyckel"))
        if max_per and per_sokord.get(nyckel, 0) >= max_per:
            continue
        post = {k: r.get(k) for k in FALT}
        post["rang"] = per_sokord.get(nyckel, 0)  # plats inom sökordet – sidan varvar sökorden med samma betyg
        per_sokord[nyckel] = post["rang"] + 1
        post["ort"], post["region"] = region_for(r.get("kalla"), r.get("plats"))
        poster.append(post)
    return poster


def _sparlista(spar_cfg: dict) -> list[dict]:
    return [{"id": sid, "namn": s.get("namn", sid), "kategorier": list(s.get("sokningar", {}).keys()),
             "sokningar": s.get("sokningar", {}), "lardomar": s.get("lardomar") or "",
             "pausade": s.get("pausade") or [], "flipp": bool(s.get("flipp"))}
            for sid, s in spar_cfg.items()]


def _nu() -> str:
    return datetime.now(ZoneInfo("Europe/Stockholm")).strftime("%-d/%-m kl %H:%M")


def anvandarfynd(db, cfg: dict) -> dict:
    """Varje användares egna spår och fynd, för att läggas upp i databasen: {user_id: {...}}."""
    egna: dict[str, dict] = {}
    for sid, s in cfg.get("spar", {}).items():
        # Huvudspåren i config.yaml tillhör administratörerna; övriga spår sin ägare.
        for uid in ([s["agare"]] if s.get("agare") else sorted(cfg.get("_admins") or [])):
            egna.setdefault(uid, {})[sid] = s
    if not egna:
        return {}
    rader = db.traffar(cfg.get("sajt_min_betyg", 6))
    return {uid: {"spar": _sparlista(spar), "poster": _poster(db, cfg, set(spar), rader), "uppdaterad": _nu()}
            for uid, spar in egna.items()}


def publika(cfg: dict) -> set[str]:
    """Spår som får visas utan inloggning: de med `publik: true` i config.yaml. Inget annat läcker ut."""
    return {sid for sid, s in cfg.get("spar", {}).items() if s.get("publik") is True}


def bygg(db, cfg: dict) -> Path:
    """Skriver site/data/fynd.json: uppdateringstid, de publika spåren och deras fynd. Returnerar filen."""
    spar_ids = publika(cfg)
    spar = [s for s in _sparlista({sid: cfg["spar"][sid] for sid in spar_ids}) if spar_ids] if spar_ids else []
    poster = _poster(db, cfg, spar_ids) if spar_ids else []
    data = {"poster": poster, "spar": spar, "uppdaterad": _nu(),
            "standard": cfg.get("min_betyg", 7), "golv": cfg.get("sajt_min_betyg", 6)}
    ut = UT / "data"
    ut.mkdir(parents=True, exist_ok=True)
    fil = ut / "fynd.json"
    fil.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"Fynddata skriven ({len(poster)} publika fynd) → {fil}")
    return fil
