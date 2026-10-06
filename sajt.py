"""Bygger hemsidan (site/index.html) från databasen. Publiceras via GitHub Pages."""
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
                  "upplands väsby", "vallentuna", "österåker", "tyresö", "botkyrka", "ekerö", "sickla", "bromma"],
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
    if kalla == "tradera":
        return "", "Okänd ort"
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
        "jamforsok", "jmf_median", "jmf_lag", "jmf_hog", "jmf_antal"]


def _poster(db, cfg: dict, spar_ids: set[str] | None, rader: list[dict] | None = None) -> list[dict]:
    """Fynden som visas, bäst först, med högst sajt_max_per_sokord per sökord och spår."""
    min_betyg = cfg.get("sajt_min_betyg", 6)
    max_per = cfg.get("sajt_max_per_sokord") or 0
    per_sokord: dict[tuple, int] = {}
    poster = []
    for r in (rader if rader is not None else db.traffar(min_betyg)):  # redan sorterade bäst först
        if spar_ids is not None and r.get("spar") not in spar_ids:
            continue
        nyckel = (r.get("spar"), r.get("sokord") or r.get("nyckel"))
        if max_per and per_sokord.get(nyckel, 0) >= max_per:
            continue
        per_sokord[nyckel] = per_sokord.get(nyckel, 0) + 1
        post = {k: r.get(k) for k in FALT}
        post["ort"], post["region"] = region_for(r.get("kalla"), r.get("plats"))
        poster.append(post)
    return poster


def _sparlista(spar_cfg: dict) -> list[dict]:
    return [{"id": sid, "namn": s.get("namn", sid), "kategorier": list(s.get("sokningar", {}).keys()),
             "sokningar": s.get("sokningar", {})}
            for sid, s in spar_cfg.items()]


def _nu() -> str:
    return datetime.now(ZoneInfo("Europe/Stockholm")).strftime("%-d/%-m kl %H:%M")


def anvandarfynd(db, cfg: dict) -> dict:
    """Varje användares egna spår och fynd, för att läggas upp i databasen: {user_id: {...}}."""
    egna: dict[str, dict] = {}
    for sid, s in cfg.get("spar", {}).items():
        if s.get("agare"):
            egna.setdefault(s["agare"], {})[sid] = s
    if not egna:
        return {}
    rader = db.traffar(cfg.get("sajt_min_betyg", 6))
    return {uid: {"spar": _sparlista(spar), "poster": _poster(db, cfg, set(spar), rader), "uppdaterad": _nu()}
            for uid, spar in egna.items()}


def bygg(db, cfg: dict) -> Path:
    min_betyg = cfg.get("sajt_min_betyg", 6)
    spar_cfg = {sid: s for sid, s in (cfg.get("spar") or {}).items() if not s.get("agare")}
    spar_cfg = spar_cfg or {"": {"namn": "Fynd", "sokningar": cfg.get("sokningar", {})}}
    forsta = next(iter(spar_cfg))
    rader = db.traffar(min_betyg)
    for r in rader:
        r["spar"] = r.get("spar") or forsta
    poster = _poster(db, cfg, set(spar_cfg), rader)
    spar = _sparlista(spar_cfg)
    nu = _nu()

    data = json.dumps(
        {"poster": poster, "spar": spar, "uppdaterad": nu,
         "standard": cfg.get("min_betyg", 7), "golv": min_betyg,
         "supabase": cfg.get("supabase") or None},
        ensure_ascii=False,
    ).replace("</", "<\\/")

    UT.mkdir(exist_ok=True)
    # Ikoner och manifest så att sidan kan installeras som app på telefonen.
    import shutil
    for f in (ROT / "assets").glob("*"):
        shutil.copy(f, UT / f.name)
    fil = UT / "index.html"
    fil.write_text(MALL.replace("__DATA__", data), encoding="utf-8")
    print(f"Hemsidan byggd: {len(poster)} fynd → {fil}")
    return fil


MALL = r"""<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#1b241f">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Fyndjakt">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" href="favicon.png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<title>Fyndjakt · The Reading Room</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #1b241f;          /* Obsidian Green-ish */
    --panel: #233029;
    --panel-2: #2a3830;
    --line: #3a4a40;
    --text: #efe6d4;
    --muted: #b3a88f;
    --brass: #c9a35b;
    --brass-dim: #8f7440;
    --cognac: #9a5b2e;
    --oxblood: #6e2a2a;
    --radius: 14px;
  }
  * { box-sizing: border-box; }
  html { -webkit-text-size-adjust: 100%; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.5 Inter, system-ui, sans-serif;
    background-image: radial-gradient(1200px 500px at 50% -200px, rgba(201,163,91,.10), transparent 70%);
    min-height: 100vh;
  }
  header { padding: calc(40px + env(safe-area-inset-top)) 16px 8px; text-align: center; }
  .tabs { display: flex; justify-content: center; gap: 4px; padding: 18px 16px 0; border-bottom: 1px solid var(--line); }
  .tab {
    background: none; border: 0; border-bottom: 2px solid transparent; color: var(--muted);
    font-family: "Cormorant Garamond", Georgia, serif; font-size: 22px; font-weight: 600;
    padding: 6px 16px 10px; cursor: pointer;
  }
  .tab[aria-selected="true"] { color: var(--text); border-bottom-color: var(--brass); }
  .tab .n { font-family: Inter, sans-serif; font-size: 12px; color: var(--brass); margin-left: 6px; font-weight: 500; }
  @media (max-width: 480px) { .tab { font-size: 19px; padding: 6px 10px 10px; } }
  .tab:focus-visible { outline: 2px solid var(--brass); outline-offset: 2px; }
  .ornament { color: var(--brass); letter-spacing: .5em; font-size: 12px; text-transform: uppercase; }
  h1 {
    font-family: "Cormorant Garamond", Georgia, serif; font-weight: 600;
    font-size: clamp(34px, 7vw, 56px); margin: 6px 0 4px; letter-spacing: .01em;
  }
  h1 em { color: var(--brass); font-style: italic; font-weight: 500; }
  .sub { color: var(--muted); margin: 0; }

  .controls {
    position: sticky; top: 0; z-index: 5; background: rgba(27,36,31,.92);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--line); padding: 12px 16px;
  }
  .row { max-width: 1200px; margin: 0 auto; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .row + .row { margin-top: 10px; }
  .chip {
    border: 1px solid var(--line); background: var(--panel); color: var(--text);
    padding: 7px 14px; border-radius: 999px; font: inherit; font-size: 14px; cursor: pointer;
  }
  .chip[aria-pressed="true"] { background: var(--brass); color: #1b1a14; border-color: var(--brass); font-weight: 600; }
  .chip:focus-visible, select:focus-visible, input:focus-visible { outline: 2px solid var(--brass); outline-offset: 2px; }
  label { color: var(--muted); font-size: 14px; display: flex; align-items: center; gap: 8px; }
  select {
    background: var(--panel); color: var(--text); border: 1px solid var(--line);
    border-radius: 10px; padding: 7px 10px; font: inherit; font-size: 14px;
  }
  input[type=range] { accent-color: var(--brass); width: 110px; }
  .count { margin-left: auto; color: var(--muted); font-size: 14px; }

  main { max-width: 1200px; margin: 0 auto; padding: 20px 16px 60px; }
  .grid { display: grid; gap: 18px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); }
  .card {
    background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    overflow: hidden; display: flex; flex-direction: column; text-decoration: none; color: inherit;
    transition: transform .15s ease, border-color .15s ease;
  }
  .card:hover { transform: translateY(-2px); border-color: var(--brass-dim); }
  .img { position: relative; aspect-ratio: 4/3; background: var(--panel-2); }
  .img img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .img .none { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted);
               font-family: "Cormorant Garamond", serif; font-size: 22px; font-style: italic; }
  .score {
    position: absolute; top: 10px; left: 10px; background: rgba(20,26,22,.88); color: var(--brass);
    border: 1px solid var(--brass-dim); border-radius: 999px; padding: 3px 10px; font-weight: 600; font-size: 13px;
  }
  .new { position: absolute; top: 10px; right: 10px; background: var(--oxblood); color: #f5e7dc;
         border: 1px solid rgba(245,231,220,.55); box-shadow: 0 1px 6px rgba(0,0,0,.4);
         border-radius: 999px; padding: 3px 10px; font-size: 12px; font-weight: 600; letter-spacing: .04em; }
  .body { padding: 14px 16px 16px; display: flex; flex-direction: column; gap: 8px; flex: 1; }
  .cat { color: var(--brass); font-size: 12px; text-transform: uppercase; letter-spacing: .12em; }
  .title { font-family: "Cormorant Garamond", Georgia, serif; font-size: 21px; line-height: 1.2; margin: 0; font-weight: 600; }
  .why { color: var(--muted); font-style: italic; margin: 0; font-size: 14px; }
  .meta { margin-top: auto; padding-top: 10px; border-top: 1px solid var(--line);
          display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 13px; color: var(--muted); }
  .price { color: var(--text); font-weight: 600; }
  .soon { color: #e9a77b; }
  .jmf { font-size: 13px; color: var(--muted); background: var(--panel-2); border: 1px solid var(--line);
         border-radius: 10px; padding: 8px 10px; display: flex; flex-wrap: wrap; gap: 4px 8px; align-items: baseline; }
  .jmf b { color: var(--text); font-weight: 600; }
  .lage { font-size: 12px; font-weight: 600; letter-spacing: .03em; border-radius: 999px; padding: 2px 9px; }
  .lage.fynd { background: #2f5a3c; color: #d9f0de; }
  .lage.bra { background: #3a4a2e; color: #e2ecc9; }
  .lage.dyrt { background: #5a2f2f; color: #f3d9d9; }
  .lage-img { position: absolute; bottom: 10px; left: 10px; }
  .empty { text-align: center; color: var(--muted); padding: 60px 16px; font-family: "Cormorant Garamond", serif; font-size: 24px; font-style: italic; }
  footer { text-align: center; color: var(--muted); font-size: 13px; padding: 0 16px 40px; }

  /* Konto och reaktioner */
  .konto { position: absolute; top: 14px; right: 16px; display: flex; gap: 8px; }
  header { position: relative; }
  .knapp {
    border: 1px solid var(--line); background: var(--panel); color: var(--text); font: inherit; font-size: 14px;
    padding: 7px 14px; border-radius: 999px; cursor: pointer;
  }
  .knapp.primar { background: var(--brass); color: #1b1a14; border-color: var(--brass); font-weight: 600; }
  .knapp:focus-visible { outline: 2px solid var(--brass); outline-offset: 2px; }
  .reakt { display: flex; gap: 6px; padding-top: 10px; }
  .reakt button {
    flex: 1; border: 1px solid var(--line); background: var(--panel-2); color: var(--muted); font: inherit;
    font-size: 13px; padding: 7px 4px; border-radius: 10px; cursor: pointer; white-space: nowrap;
  }
  .reakt button[aria-pressed="true"] { color: var(--text); border-color: var(--brass); background: #3a3524; }
  .reakt button:focus-visible { outline: 2px solid var(--brass); outline-offset: 1px; }
  .card.borta { opacity: 0; transform: scale(.97); transition: opacity .35s, transform .35s; }

  /* Panel: logga in / Min smak */
  .panel-bak { position: fixed; inset: 0; background: rgba(8,12,10,.7); z-index: 20; display: flex;
               justify-content: center; align-items: flex-start; overflow-y: auto; padding: 24px 12px; }
  .panel-bak[hidden] { display: none; }
  .panel { background: var(--bg); border: 1px solid var(--line); border-radius: 18px; width: min(680px, 100%);
           padding: 22px 18px 26px; box-shadow: 0 20px 60px rgba(0,0,0,.5); }
  .panel h2 { font-family: "Cormorant Garamond", Georgia, serif; font-size: 30px; margin: 0 0 4px; }
  .panel h3 { font-family: "Cormorant Garamond", Georgia, serif; font-size: 22px; margin: 26px 0 8px;
              border-top: 1px solid var(--line); padding-top: 18px; }
  .panel p.hj { color: var(--muted); margin: 0 0 12px; font-size: 14px; }
  .panel .stang { float: right; }
  .falt { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 8px 0; }
  .falt input[type=text], .falt input[type=email], .falt select {
    flex: 1 1 200px; background: var(--panel); color: var(--text); border: 1px solid var(--line);
    border-radius: 10px; padding: 9px 11px; font: inherit; font-size: 15px; min-width: 0;
  }
  .kamera { display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center;
            border: 1px dashed var(--brass-dim); border-radius: 14px; padding: 18px; background: var(--panel); }
  .kamera label.knapp { display: inline-block; }
  .kamera input[type=file] { position: absolute; width: 1px; height: 1px; opacity: 0; }
  .forhand { max-width: 100%; max-height: 260px; border-radius: 10px; display: block; margin: 0 auto; }
  .tolkning { background: var(--panel-2); border: 1px solid var(--line); border-radius: 12px; padding: 12px; margin-top: 12px; text-align: left; width: 100%; }
  .t-huvud { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px; }
  .t-huvud b { font-family: "Cormorant Garamond", Georgia, serif; font-size: 23px; line-height: 1.2; }
  .sak { font-size: 12px; font-weight: 600; border-radius: 999px; padding: 2px 9px; }
  .sak.hög { background: #2f5a3c; color: #d9f0de; } .sak.medel { background: #4a4425; color: #f0e6c4; }
  .sak.låg { background: #4a3030; color: #f0d6d6; }
  .t-alt { color: var(--muted); font-size: 14px; margin-top: 2px; }
  .t-beskr { color: var(--muted); font-size: 14px; margin: 6px 0 0; }
  .t-tips { margin-top: 8px; padding: 9px 11px; border-radius: 10px; font-size: 14px;
            background: #3a3524; border: 1px dashed var(--brass); color: var(--text); }
  .t-tips[hidden] { display: none; }
  .tolkning input[type=file] { position: absolute; width: 1px; height: 1px; opacity: 0; }
  .foto-rad { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }
  .foto-rad[hidden] { display: none; }
  .foto-rad img { height: 120px; max-width: 46%; object-fit: cover; border-radius: 10px; }
  .foto-rad img:only-child { height: auto; max-height: 260px; max-width: 100%; }
  .samtal { display: flex; flex-direction: column; gap: 6px; margin: 8px 0 4px; }
  .samtal p { margin: 0; padding: 8px 11px; border-radius: 12px; font-size: 14px; max-width: 90%; }
  .samtal .du { align-self: flex-end; background: #3a3524; color: var(--text); border: 1px solid var(--brass-dim); }
  .samtal .claude { align-self: flex-start; background: var(--panel); color: var(--text); border: 1px solid var(--line); }
  .lista { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
  .lista li { display: flex; gap: 10px; align-items: center; background: var(--panel); border: 1px solid var(--line);
              border-radius: 10px; padding: 7px 8px; font-size: 14px; }
  .lista img { width: 44px; height: 44px; object-fit: cover; border-radius: 6px; flex: none; background: var(--panel-2); }
  .lista .txt { flex: 1; min-width: 0; }
  .lista .txt a { color: var(--text); }
  .lista .etik { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--brass); display: block; }
  .lista .bort { background: none; border: 0; color: var(--muted); font-size: 18px; cursor: pointer; padding: 4px 8px; }
  .tom { color: var(--muted); font-size: 14px; font-style: italic; }
  .ingen-profil { max-width: 560px; margin: 8px auto 0; padding: 10px 14px; text-align: center; font-size: 14px;
                  color: var(--text); background: var(--panel); border: 1px solid var(--brass-dim); border-radius: 12px; }
  .ingen-profil[hidden] { display: none; }
  .status { font-size: 14px; color: var(--brass); min-height: 1.4em; }
  .knapp.google { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%;
                  background: #fff; color: #1f1f1f; border-color: #fff; font-weight: 600; padding: 11px 14px; margin: 14px 0 6px; }
  .panel p.hj.eller { text-align: center; margin: 10px 0 4px; }
  textarea { width: 100%; background: var(--panel); color: var(--text); border: 1px solid var(--line); border-radius: 10px;
             padding: 9px 11px; font: inherit; font-size: 15px; resize: vertical; }
  textarea:focus-visible, input[type=number]:focus-visible { outline: 2px solid var(--brass); outline-offset: 2px; }
  .profilkort { background: var(--panel-2); border: 1px solid var(--line); border-radius: 14px; padding: 14px; margin-top: 14px; }
  .profilkort label.rubr { display: block; color: var(--text); font-weight: 600; font-size: 14px; margin: 12px 0 4px; }
  .profilkort label.rubr small { color: var(--muted); font-weight: 400; }
  .profilkort input[type=text], .profilkort input[type=number], .admin input[type=email] {
    width: 100%; background: var(--panel); color: var(--text); border: 1px solid var(--line);
    border-radius: 10px; padding: 9px 11px; font: inherit; font-size: 15px; }
  .profilkort .fil { position: absolute; width: 1px; height: 1px; opacity: 0; }
  .profilkort .kommentar { color: var(--muted); font-size: 14px; font-style: italic; margin: 6px 0 0; }
  .valkommen { background: #3a3524; border: 1px dashed var(--brass); border-radius: 12px; padding: 12px 14px; font-size: 14px; margin: 10px 0 0; }
  .valkommen[hidden] { display: none; }
  .profilval { display: flex; align-items: center; gap: 10px; margin-top: 16px; }
  .profilval label { color: var(--text); font-weight: 600; font-size: 14px; }
  .profilval select { flex: 1; font-size: 15px; padding: 10px 12px; border-color: var(--brass-dim); }
  .filspar .kat { color: var(--brass); font-size: 12px; text-transform: uppercase; letter-spacing: .1em; margin: 12px 0 6px; }
  .filspar .ord { display: flex; flex-wrap: wrap; gap: 6px; }
  .filspar .ord span { background: var(--panel); border: 1px solid var(--line); border-radius: 999px; padding: 3px 10px; font-size: 13px; }
  @media (max-width: 560px) { .konto { position: static; justify-content: center; margin-bottom: 10px; } }
</style>
</head>
<body>
<header>
  <div class="konto" id="konto" hidden>
    <button class="knapp" id="b-prof" type="button" hidden>Mina bevakningar</button>
    <button class="knapp" id="b-smak" type="button" hidden>Min smak</button>
    <button class="knapp" id="b-logga" type="button">Logga in</button>
  </div>
  <div class="ornament">✦ Fyndjakt ✦</div>
  <h1>Dagens <em>fynd</em></h1>
  <p class="sub">Utvalt från svenska auktioner och second hand · uppdaterad <span id="upd"></span></p>
</header>

<p class="ingen-profil" id="ingen-profil" hidden>Du är inloggad men inte inbjuden till Fyndjakt än. Be den som tipsade dig om appen att bjuda in din e-post.</p>
<nav class="tabs" id="tabs" role="tablist" aria-label="Spår"></nav>

<div class="controls">
  <div class="row" id="cats" role="group" aria-label="Kategori"></div>
  <div class="row">
    <label>Sortera
      <select id="sort">
        <option value="betyg">Bäst matchning</option>
        <option value="ny">Nyast</option>
        <option value="slut">Slutar snart</option>
        <option value="pris">Lägst pris</option>
        <option value="lage">Bäst pris mot liknande</option>
      </select>
    </label>
    <label>Område
      <select id="reg"><option value="">Hela Sverige</option></select>
    </label>
    <label>Källa
      <select id="src"><option value="">Alla</option></select>
    </label>
    <label>Minst <input id="min" type="range" min="0" max="10" step="1"> <span id="minv"></span>/10</label>
    <span class="count" id="count"></span>
  </div>
</div>

<main>
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" hidden>Inga fynd med de här filtren ännu.</div>
</main>
<div class="panel-bak" id="p-login" hidden>
  <div class="panel" role="dialog" aria-modal="true" aria-labelledby="login-rubrik">
    <button class="knapp stang" type="button" data-stang>Stäng</button>
    <h2 id="login-rubrik">Logga in</h2>
    <button class="knapp google" type="button" id="b-google">
      <svg viewBox="0 0 48 48" width="18" height="18" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.6 5.4 2.6 13.3l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.7 6c4.5-4.2 6.9-10.3 6.9-17.7z"/><path fill="#FBBC05" d="M10.5 28.6c-.5-1.4-.8-3-.8-4.6s.3-3.2.8-4.6l-7.9-6.1C1 16.6 0 20.2 0 24s1 7.4 2.6 10.7l7.9-6.1z"/><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.7-6c-2.2 1.5-5 2.3-8.2 2.3-6.3 0-11.6-4.1-13.5-9.9l-7.9 6.1C6.6 42.6 14.6 48 24 48z"/></svg>
      Fortsätt med Google
    </button>
    <p class="hj eller">eller få en inloggningslänk till din e-post – inget lösenord behövs</p>
    <form class="falt" id="f-login">
      <input type="email" id="login-epost" required placeholder="din@epost.se" autocomplete="email">
      <button class="knapp primar" type="submit">Skicka länk</button>
    </form>
    <div class="status" id="login-status" role="status"></div>
  </div>
</div>

<div class="panel-bak" id="p-prof" hidden>
  <div class="panel" role="dialog" aria-modal="true" aria-labelledby="prof-rubrik">
    <button class="knapp stang" type="button" data-stang>Stäng</button>
    <h2 id="prof-rubrik">Mina bevakningar</h2>
    <p class="hj">Beskriv vad du letar efter – ditt hem, din stil eller din samling. Varje morgon letar appen på
      Auctionet, Bukowskis, Myrorna och Stadsmissionen, och Claude väljer ut det som passar dig.
      Dina fynd syns bara för dig när du är inloggad. Du kan ha upp till tre bevakningar, t.ex. en för hemmet och en för en samling.</p>
    <p class="valkommen" id="valkommen" hidden>Välkommen! Börja med att skriva några rader om vad du gillar nedan och tryck på
      <b>✨ Föreslå sökord</b>. Spara – så kommer dina första fynd i morgon bitti.</p>
    <p class="valkommen" id="admin-info" hidden><b>The Reading Room</b> och <b>Samlingen</b> styrs av dina filer
      stil.md och samlingsprofil.md och syns för alla. Här kan du lägga till extra bevakningar som bara du ser,
      och längre ner bjuda in andra.</p>
    <div class="profilval">
      <label for="prof-val">Bevakning</label>
      <select id="prof-val"></select>
    </div>
    <div id="prof-lista"></div>

    <section class="admin" id="admin" hidden>
      <h3>Användare</h3>
      <p class="hj">Bjud in någon med e-post. Hen loggar sedan in på sidan med samma adress och skapar sina egna bevakningar.</p>
      <form class="falt" id="f-bjud">
        <input type="email" id="bjud-epost" required placeholder="kompis@epost.se" autocomplete="off" style="flex:1 1 220px">
        <button class="knapp primar" type="submit">Bjud in</button>
      </form>
      <div class="status" id="bjud-status" role="status"></div>
      <ul class="lista" id="l-medlemmar"></ul>
    </section>
  </div>
</div>

<div class="panel-bak" id="p-smak" hidden>
  <div class="panel" role="dialog" aria-modal="true" aria-labelledby="smak-rubrik">
    <button class="knapp stang" type="button" data-stang>Stäng</button>
    <h2 id="smak-rubrik">Min smak</h2>
    <p class="hj">Det här lär sig appen av. Allt du lägger till eller tar bort här används från nästa morgon.</p>

    <div class="kamera">
      <div>📷 <strong>Fota något</strong> – så känner Claude igen föremålet</div>
      <label class="knapp primar" for="foto">Ta foto eller välj bild</label>
      <input type="file" id="foto" accept="image/*" capture="environment">
      <div class="foto-rad" id="foto-rad" hidden></div>
      <div class="status" id="foto-status" role="status"></div>
      <div class="tolkning" id="tolkning" hidden>
        <div class="t-huvud"><b id="t-gissning"></b> <span class="sak" id="t-sak"></span></div>
        <div class="t-alt" id="t-alt"></div>
        <p class="t-beskr" id="t-beskr"></p>
        <div class="samtal" id="t-samtal" aria-live="polite"></div>
        <div class="t-tips" id="t-tips" hidden></div>
        <div class="falt">
          <label class="knapp" for="foto-extra" id="l-extra">📷 Lägg till en bild till</label>
          <input type="file" id="foto-extra" accept="image/*" capture="environment">
        </div>
        <form class="falt" id="f-samtal">
          <input type="text" id="t-meddelande" maxlength="500" placeholder="Rätta eller berätta mer …" aria-label="Rätta eller berätta mer för Claude">
          <button class="knapp" type="submit">Skicka</button>
        </form>
        <div class="falt"><label for="t-sok" style="color:var(--muted);font-size:14px">Söker efter</label><input type="text" id="t-sok"></div>
        <div class="falt"><select id="t-spar"></select></div>
        <div class="falt">
          <button class="knapp primar" type="button" data-spara="gillar">👍 Gillar sånt här</button>
          <button class="knapp" type="button" data-spara="har">🏠 Har redan</button>
          <button class="knapp" type="button" data-spara="ogillar">👎 Inte min stil</button>
        </div>
      </div>
    </div>

    <h3>Säg det med egna ord</h3>
    <form class="falt" id="f-anteckning">
      <select id="a-typ">
        <option value="gillar">Jag gillar</option>
        <option value="ogillar">Jag vill inte ha</option>
        <option value="har">Jag har redan</option>
      </select>
      <input type="text" id="a-text" maxlength="300" required placeholder="t.ex. gamla sjökort i ram">
      <select id="a-spar"></select>
      <button class="knapp primar" type="submit">Lägg till</button>
    </form>

    <h3>Mina anteckningar</h3>
    <ul class="lista" id="l-anteckningar"></ul>
    <h3>👍 Gillade fynd</h3>
    <ul class="lista" id="l-gillar"></ul>
    <h3>🛒 Köpt</h3>
    <ul class="lista" id="l-kopt"></ul>
    <h3>👎 Inte min stil</h3>
    <ul class="lista" id="l-ogillar"></ul>
  </div>
</div>

<footer>Bedömt av Claude mot dina profiler · "Liknande sålt" är mittersta hälften av slutpriserna för jämförbara föremål på Auctionet de senaste 5 åren – pågående auktioner kan stiga · Länkarna går till auktionen/annonsen</footer>

<script>
const D = __DATA__;
// Det som visas just nu: de publika spåren, eller den inloggades egna.
const V = { spar: D.spar, poster: D.poster, egna: new Set() };
const st = { spar: (D.spar[0] || {}).id, cat: "", src: "", reg: "", min: D.standard, sort: "betyg" };
try { st.reg = localStorage.getItem("fyndjakt-omrade") || ""; } catch (e) {}
const $ = (id) => document.getElementById(id);
const NU = Date.now() / 1000;
const KALLNAMN = { auctionet: "Auctionet", tradera: "Tradera", bukowskis: "Bukowskis", myrorna: "Myrorna", stadsmissionen: "Stadsmissionen" };
const REGORDNING = ["Stockholm", "Uppsala och Mälardalen", "Östergötland, Småland och Blekinge", "Västsverige och Värmland",
  "Skåne", "Norrland och Dalarna", "Övriga Sverige", "Okänd ort"];
function byggFilter() {
  const finns = new Set(V.poster.map(p => p.region));
  let sparad = st.reg;
  try { sparad = localStorage.getItem("fyndjakt-omrade") || ""; } catch (e) {}
  $("reg").replaceChildren(new Option("Hela Sverige", ""), ...REGORDNING.filter(r => finns.has(r)).map(r => new Option(r, r)));
  st.reg = finns.has(sparad) ? sparad : "";
  $("reg").value = st.reg;
  $("src").replaceChildren(new Option("Alla", ""),
    ...[...new Set(V.poster.map(p => p.kalla))].sort().map(k => new Option(KALLNAMN[k] || k, k)));
  st.src = ""; $("src").value = "";
}
byggFilter();

$("upd").textContent = D.uppdaterad;
$("min").min = D.golv; $("min").value = st.min; $("minv").textContent = st.min;

function chip(label, value) {
  const b = document.createElement("button");
  b.className = "chip"; b.textContent = label; b.type = "button";
  b.setAttribute("aria-pressed", String(st.cat === value));
  b.onclick = () => { st.cat = value; renderChips(); render(); };
  return b;
}
function aktivtSpar() { return V.spar.find(s => s.id === st.spar) || { kategorier: [] }; }
function renderTabs() {
  const t = $("tabs"); t.hidden = V.spar.length < 2;
  t.replaceChildren(...V.spar.map(s => {
    const b = document.createElement("button");
    b.className = "tab"; b.type = "button"; b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(s.id === st.spar));
    b.textContent = s.namn;
    const n = document.createElement("span"); n.className = "n";
    n.textContent = V.poster.filter(p => p.spar === s.id && p.betyg >= st.min && (!st.reg || p.region === st.reg)).length;
    b.appendChild(n);
    b.onclick = () => { st.spar = s.id; st.cat = ""; renderTabs(); renderChips(); render(); };
    return b;
  }));
}
function renderChips() {
  const c = $("cats"); c.replaceChildren(chip("Allt", ""));
  aktivtSpar().kategorier.forEach(k => c.appendChild(chip(k, k)));
}
function seddTs(p) { return p.sedd ? Date.parse(p.sedd.replace(" ", "T") + "Z") / 1000 : 0; }

function card(p) {
  const a = document.createElement("a");
  a.className = "card"; a.href = p.url; a.target = "_blank"; a.rel = "noopener";

  const img = document.createElement("div"); img.className = "img";
  if (p.bilder && p.bilder.length) {
    const i = document.createElement("img");
    i.src = p.bilder[0]; i.alt = ""; i.loading = "lazy"; i.referrerPolicy = "no-referrer";
    i.onerror = () => { i.remove(); img.insertAdjacentHTML("afterbegin", '<div class="none">Ingen bild</div>'); };
    img.appendChild(i);
  } else img.insertAdjacentHTML("afterbegin", '<div class="none">Ingen bild</div>');
  const s = document.createElement("span"); s.className = "score"; s.textContent = "★ " + p.betyg + "/10"; img.appendChild(s);
  if (NU - seddTs(p) < 86400 * 1.5) { const n = document.createElement("span"); n.className = "new"; n.textContent = "NY"; img.appendChild(n); }
  a.appendChild(img);

  const b = document.createElement("div"); b.className = "body";
  const add = (tag, cls, txt) => { if (!txt) return; const e = document.createElement(tag); e.className = cls; e.textContent = txt; b.appendChild(e); };
  add("div", "cat", p.kategori);
  add("h2", "title", p.titel);
  add("p", "why", p.motivering);
  const m = document.createElement("div"); m.className = "meta";
  const mm = (cls, txt) => { if (!txt) return; const e = document.createElement("span"); e.className = cls; e.textContent = txt; m.appendChild(e); };
  mm("price", p.pris_text);
  const j = jmf(p);
  if (j) {
    const box = document.createElement("div"); box.className = "jmf";
    const t = document.createElement("span");
    t.append("Liknande sålt: ");
    const v = document.createElement("b"); v.textContent = Math.round(p.jmf_lag).toLocaleString("sv-SE") + "–" + kr(p.jmf_hog); t.append(v);
    t.append(" · " + p.jmf_antal + " st");
    box.appendChild(t);
    if (j.klass) { const l = document.createElement("span"); l.className = "lage " + j.klass; l.textContent = j.text; box.appendChild(l); }
    b.appendChild(box);
  }
  mm("", p.plats);
  if (p.slutar) mm(p.slutar_ts && p.slutar_ts - NU < 86400 * 2 ? "soon" : "", "Slutar " + p.slutar);
  mm("", KALLNAMN[p.kalla] || p.kalla);
  b.appendChild(m);
  if (konto.inloggad) b.appendChild(reaktionsknappar(p, a));
  a.appendChild(b);
  return a;
}

function kr(n) { return Math.round(n).toLocaleString("sv-SE") + " kr"; }
// Jämför nuvarande pris med vad liknande föremål sålts för. Pågående auktioner kan fortfarande stiga.
function jmf(p) {
  if (!p.jmf_median || !p.jmf_antal || p.jmf_antal < 3) return null;
  if (!p.pris) return { kvot: null };
  const kvot = p.pris / p.jmf_median;
  if (p.jmf_antal < 5) return { kvot };  // för få försäljningar för en säker etikett
  // En auktion med flera dagar kvar har ofta låga bud som kommer att stiga.
  const tidig = p.slutar_ts && p.slutar_ts - NU > 2 * 86400;
  if (kvot <= 0.5) return tidig ? { kvot, klass: "bra", text: "Lågt bud just nu" } : { kvot, klass: "fynd", text: "Fyndläge" };
  if (kvot <= 0.8) return { kvot, klass: "bra", text: tidig ? "Lågt bud just nu" : "Under typiskt pris" };
  if (kvot >= 1.6) return { kvot, klass: "dyrt", text: "Över typiskt pris" };
  return { kvot };
}

function render() {
  let l = V.poster.filter(p =>
    p.spar === st.spar && !dold(p) && (!st.reg || p.region === st.reg) && (!st.cat || p.kategori === st.cat) && (!st.src || p.kalla === st.src) && p.betyg >= st.min);
  const s = {
    betyg: (a, b) => b.betyg - a.betyg || seddTs(b) - seddTs(a),
    ny: (a, b) => seddTs(b) - seddTs(a),
    slut: (a, b) => (a.slutar_ts || 9e12) - (b.slutar_ts || 9e12),
    pris: (a, b) => (a.pris ?? 9e12) - (b.pris ?? 9e12),
    lage: (a, b) => ((jmf(a) || {}).kvot ?? 9e12) - ((jmf(b) || {}).kvot ?? 9e12),
  }[st.sort];
  l.sort(s);
  $("grid").replaceChildren(...l.map(card));
  $("empty").hidden = l.length > 0;
  const forst = V.egna.has(st.spar) && !V.poster.some(p => p.spar === st.spar);
  $("empty").textContent = !V.spar.length ? "Skapa en bevakning under ”Mina bevakningar” så börjar appen leta åt dig."
    : forst ? "Appen letar efter det här varje morgon – dina första fynd kommer i morgon bitti."
    : "Inga fynd med de här filtren ännu.";
  $("count").textContent = l.length + (l.length === 1 ? " fynd" : " fynd");
}

$("sort").onchange = e => { st.sort = e.target.value; render(); };
$("src").onchange = e => { st.src = e.target.value; render(); };
$("reg").onchange = e => {
  st.reg = e.target.value; renderTabs(); render();
  try { localStorage.setItem("fyndjakt-omrade", st.reg); } catch (e) {}
};
$("min").oninput = e => { st.min = +e.target.value; $("minv").textContent = st.min; renderTabs(); render(); };
// ── Konto, reaktioner och Min smak (Supabase) ─────────────────────────
const konto = { sb: null, inloggad: false, admin: false, reakt: new Map(), anteckningar: [], profiler: [], fynd: null };
const TYPNAMN = { gillar: "👍 Gillar", ogillar: "👎 Inte min stil", kopt: "🛒 Köpt" };
const ANT_NAMN = { gillar: "Gillar", ogillar: "Vill inte ha", har: "Har redan" };

function dold(p) { const r = konto.reakt.get(p.nyckel); return r && (r.typ === "ogillar" || r.typ === "kopt"); }

function reaktionsknappar(p, kortEl) {
  const rad = document.createElement("div"); rad.className = "reakt";
  for (const typ of ["gillar", "ogillar", "kopt"]) {
    const btn = document.createElement("button"); btn.type = "button";
    btn.textContent = TYPNAMN[typ];
    btn.setAttribute("aria-pressed", String((konto.reakt.get(p.nyckel) || {}).typ === typ));
    btn.onclick = async (e) => {
      e.preventDefault(); e.stopPropagation();
      const nu = (konto.reakt.get(p.nyckel) || {}).typ;
      if (nu === typ) await taBortReaktion(p.nyckel);
      else await sparaReaktion(p, typ);
      if (typ !== "gillar" && nu !== typ) {
        kortEl.classList.add("borta");
        setTimeout(() => { renderTabs(); render(); }, 380);
      } else { renderTabs(); render(); }
    };
    rad.appendChild(btn);
  }
  return rad;
}

async function sparaReaktion(p, typ) {
  const rad = { nyckel: p.nyckel, typ, spar: p.spar, kategori: p.kategori, titel: p.titel, url: p.url,
                bild: (p.bilder || [])[0] || null, pris_text: p.pris_text, motivering: p.motivering };
  konto.reakt.set(p.nyckel, rad);
  const { error } = await konto.sb.from("fyndjakt_reaktioner").upsert(rad, { onConflict: "user_id,nyckel" });
  if (error) { alertFel(error); konto.reakt.delete(p.nyckel); }
}
async function taBortReaktion(nyckel) {
  const gammal = konto.reakt.get(nyckel);
  konto.reakt.delete(nyckel);
  const { error } = await konto.sb.from("fyndjakt_reaktioner").delete().eq("nyckel", nyckel);
  if (error) { alertFel(error); if (gammal) konto.reakt.set(nyckel, gammal); }
}
function alertFel(error) { console.error(error); visaStatus("foto-status", "Något gick fel – försök igen."); }
function visaStatus(id, text) { const e = $(id); if (e) e.textContent = text; }

async function laddaMittData() {
  const [r, a] = await Promise.all([
    konto.sb.from("fyndjakt_reaktioner").select("*").order("skapad", { ascending: false }),
    konto.sb.from("fyndjakt_anteckningar").select("*").order("skapad", { ascending: false }),
  ]);
  konto.reakt = new Map((r.data || []).map(x => [x.nyckel, x]));
  konto.anteckningar = a.data || [];
}

function oppna(id) { $(id).hidden = false; const f = $(id).querySelector("input,button"); if (f) f.focus(); }
function stang(id) { $(id).hidden = true; }
document.querySelectorAll("[data-stang]").forEach(b => b.onclick = () => stang(b.closest(".panel-bak").id));
document.querySelectorAll(".panel-bak").forEach(bak => bak.addEventListener("click", e => { if (e.target === bak) stang(bak.id); }));
document.addEventListener("keydown", e => { if (e.key === "Escape") document.querySelectorAll(".panel-bak").forEach(b => b.hidden = true); });

function sparVal(select, standard) {
  select.replaceChildren(new Option("Alla flikar", ""), ...V.spar.map(s => new Option(s.namn, s.id)));
  select.value = standard || "";
}

function listrad({ bild, etikett, titel, url, onBort }) {
  const li = document.createElement("li");
  if (bild !== undefined) { const i = document.createElement("img"); if (bild) i.src = bild; i.alt = ""; i.referrerPolicy = "no-referrer"; li.appendChild(i); }
  const t = document.createElement("div"); t.className = "txt";
  if (etikett) { const s = document.createElement("span"); s.className = "etik"; s.textContent = etikett; t.appendChild(s); }
  if (url) { const a = document.createElement("a"); a.href = url; a.target = "_blank"; a.rel = "noopener"; a.textContent = titel; t.appendChild(a); }
  else t.append(titel);
  li.appendChild(t);
  const x = document.createElement("button"); x.className = "bort"; x.type = "button"; x.textContent = "✕";
  x.setAttribute("aria-label", "Ta bort " + titel); x.onclick = onBort; li.appendChild(x);
  return li;
}

function renderSmak() {
  const sparNamn = id => (V.spar.find(s => s.id === id) || {}).namn || "Alla flikar";
  const ant = $("l-anteckningar");
  ant.replaceChildren(...konto.anteckningar.map(a => listrad({
    etikett: ANT_NAMN[a.typ] + " · " + sparNamn(a.spar) + (a.sokord ? " · söker ”" + a.sokord + "”" : ""),
    titel: a.text,
    onBort: async () => {
      konto.anteckningar = konto.anteckningar.filter(x => x.id !== a.id);
      await konto.sb.from("fyndjakt_anteckningar").delete().eq("id", a.id);
      renderSmak();
    },
  })));
  if (!konto.anteckningar.length) ant.innerHTML = '<li class="tom">Inga ännu – fota något eller skriv med egna ord.</li>';
  for (const typ of ["gillar", "kopt", "ogillar"]) {
    const ul = $("l-" + typ);
    const rader = [...konto.reakt.values()].filter(r => r.typ === typ);
    ul.replaceChildren(...rader.map(r => listrad({
      bild: r.bild || "", etikett: sparNamn(r.spar), titel: r.titel, url: r.url,
      onBort: async () => { await taBortReaktion(r.nyckel); renderSmak(); renderTabs(); render(); },
    })));
    if (!rader.length) ul.innerHTML = '<li class="tom">Inget här ännu.</li>';
  }
}

async function sparaAnteckning(typ, text, spar, sokord) {
  text = (text || "").trim();
  if (!text) { visaStatus("foto-status", "Skriv något först."); return false; }
  const rad = { typ, text: text.slice(0, 300), spar: spar || null, sokord: typ === "gillar" && sokord ? sokord.slice(0, 60) : null };
  const { data, error } = await konto.sb.from("fyndjakt_anteckningar").insert(rad).select().single();
  if (error) { console.error(error); visaStatus("foto-status", "Kunde inte spara – försök igen."); return false; }
  konto.anteckningar.unshift(data); renderSmak(); return true;
}

$("f-anteckning").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("a-text").value.trim(); if (!text) return;
  if (await sparaAnteckning($("a-typ").value, text, $("a-spar").value, $("a-typ").value === "gillar" ? text.split(/\s+/).slice(0, 4).join(" ") : null))
    $("a-text").value = "";
};

// Foto → nedskalad JPEG → Claude känner igen föremålet
function skalaNer(fil, max = 1280) {
  return new Promise((ok, fel) => {
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement("canvas"); c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src); ok(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = fel; img.src = URL.createObjectURL(fil);
  });
}
let senasteTolkning = null;
let fotoBilder = [];  // alla bilder av föremålet (data-URL:er), max 4
let samtal = [];      // [{roll: "anvandare"|"claude", text, visa}]

function visaBilder() {
  $("foto-rad").replaceChildren(...fotoBilder.map((src, i) => {
    const im = document.createElement("img"); im.src = src; im.alt = "Bild " + (i + 1); return im;
  }));
  $("foto-rad").hidden = !fotoBilder.length;
  $("l-extra").hidden = fotoBilder.length >= 4;
}
function visaTolkning(svar) {
  senasteTolkning = svar;
  $("t-gissning").textContent = svar.gissning || svar.beskrivning || "Okänt föremål";
  const sak = (svar.sakerhet || "").toLowerCase();
  $("t-sak").textContent = { "hög": "Ganska säker", "medel": "Rimlig gissning", "låg": "Osäker" }[sak] || "";
  $("t-sak").className = "sak " + sak;
  $("t-alt").textContent = svar.alternativ ? "Kanske också: " + svar.alternativ : "";
  $("t-beskr").textContent = svar.gissning && svar.beskrivning !== svar.gissning ? svar.beskrivning : "";
  $("t-tips").textContent = svar.tips ? "💡 " + svar.tips : "";
  $("t-tips").hidden = !svar.tips;
  $("t-sok").value = svar.sokord || "";
  $("tolkning").hidden = false;
}
function visaSamtal() {
  $("t-samtal").replaceChildren(...samtal.filter(s => s.visa).map(s => {
    const p = document.createElement("p"); p.className = s.roll === "claude" ? "claude" : "du"; p.textContent = s.visa; return p;
  }));
}
async function fragaClaude() {
  const body = { bilder: fotoBilder, mediatyp: "image/jpeg", samtal: samtal.map(s => ({ roll: s.roll, text: s.text })) };
  const { data: svar, error } = await konto.sb.functions.invoke("fyndjakt-kann-igen", { body });
  if (error || !svar || svar.fel) {
    let txt = (svar && svar.fel) || "";
    try { if (!txt && error && error.context) txt = (await error.context.json()).fel; } catch (x) {}
    throw new Error(txt || "Kunde inte känna igen bilden just nu.");
  }
  samtal.push({ roll: "claude", text: JSON.stringify(svar), visa: svar.svar || "" });
  visaSamtal(); visaTolkning(svar);
  return svar;
}
async function laggTillFoto(fil, forsta) {
  const data = await skalaNer(fil);
  if (forsta) { fotoBilder = [data]; samtal = []; }
  else {
    fotoBilder.push(data);
    samtal.push({ roll: "anvandare", text: "Här är en bild till av samma föremål (bild " + fotoBilder.length + ").", visa: "📷 Bild " + fotoBilder.length });
  }
  visaBilder(); visaSamtal();
}

$("foto").onchange = async (e) => {
  const fil = e.target.files[0]; if (!fil) return;
  $("tolkning").hidden = true; visaStatus("foto-status", "Claude tittar på bilden …");
  try {
    await laggTillFoto(fil, true);
    sparVal($("t-spar"), st.spar);
    await fragaClaude();
    visaStatus("foto-status", "");
  } catch (x) { console.error(x); visaStatus("foto-status", x.message || "Kunde inte läsa bilden."); }
  finally { e.target.value = ""; }
};
$("foto-extra").onchange = async (e) => {
  const fil = e.target.files[0]; if (!fil || !fotoBilder.length) return;
  visaStatus("foto-status", "Claude tittar på den nya bilden …");
  try { await laggTillFoto(fil, false); await fragaClaude(); visaStatus("foto-status", ""); }
  catch (x) { console.error(x); visaStatus("foto-status", x.message || "Kunde inte läsa bilden."); }
  finally { e.target.value = ""; }
};
$("f-samtal").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("t-meddelande").value.trim();
  if (!text || !fotoBilder.length) return;
  samtal.push({ roll: "anvandare", text, visa: text });
  $("t-meddelande").value = ""; visaSamtal();
  visaStatus("foto-status", "Claude funderar …");
  try { await fragaClaude(); visaStatus("foto-status", ""); } catch (x) { visaStatus("foto-status", x.message); }
};
document.querySelectorAll("[data-spara]").forEach(b => b.onclick = async () => {
  if (!senasteTolkning) return;
  const sok = $("t-sok").value.trim();
  const text = (senasteTolkning.beskrivning || "").trim() || sok || "Fotat föremål";
  const ok = await sparaAnteckning(b.dataset.spara, text, $("t-spar").value, sok);
  if (ok) {
    $("tolkning").hidden = true; senasteTolkning = null; fotoBilder = []; samtal = []; visaSamtal(); visaBilder();
    visaStatus("foto-status", b.dataset.spara === "gillar" ? "Sparat! Appen letar efter liknande från i morgon." : "Sparat!");
  }
});

$("b-google").onclick = async () => {
  visaStatus("login-status", "Öppnar Google …");
  const { error } = await konto.sb.auth.signInWithOAuth({
    provider: "google", options: { redirectTo: location.origin + location.pathname, queryParams: { prompt: "select_account" } },
  });
  if (error) { console.error(error); visaStatus("login-status", "Google-inloggningen är inte påslagen än – använd e-postlänken så länge."); }
};

$("f-login").onsubmit = async (e) => {
  e.preventDefault();
  visaStatus("login-status", "Skickar …");
  const email = $("login-epost").value.trim();
  // Inbjudna som inte har ett konto än får ett skapat; andra kan bara logga in om de redan finns.
  const { data: inbjuden } = await konto.sb.rpc("fyndjakt_ar_inbjuden", { epost: email });
  const { error } = await konto.sb.auth.signInWithOtp({
    email, options: { emailRedirectTo: location.origin + location.pathname, shouldCreateUser: !!inbjuden },
  });
  visaStatus("login-status", error ? "Det gick inte – är det rätt e-post?" : "Klart! Öppna länken i mejlet på den här enheten.");
};

async function uppdateraKonto(session) {
  konto.inloggad = !!session;
  $("b-logga").textContent = session ? "Logga ut" : "Logga in";
  $("b-smak").hidden = $("b-prof").hidden = !session;
  konto.admin = false; konto.profiler = []; konto.fynd = null;
  if (session) {
    const { data: medlem } = await konto.sb.rpc("fyndjakt_ga_med");
    if (!medlem) { konto.inloggad = false; $("b-smak").hidden = $("b-prof").hidden = true; $("ingen-profil").hidden = false; }
    else {
      const [jag, prof, fynd] = await Promise.all([
        konto.sb.from("fyndjakt_anvandare").select("admin").maybeSingle(),
        konto.sb.from("fyndjakt_profiler").select("*").order("id"),
        konto.sb.from("fyndjakt_fynd").select("data").maybeSingle(),
        laddaMittData(),
      ]);
      konto.admin = !!(jag.data && jag.data.admin);
      konto.profiler = prof.data || [];
      konto.fynd = (fynd.data && fynd.data.data) || null;
    }
  } else { konto.reakt = new Map(); konto.anteckningar = []; $("ingen-profil").hidden = true; }
  byggVy();
  if (konto.inloggad && !konto.admin && !konto.profiler.length) oppnaProfiler(true);
}

// Publika spår (för administratören) + egna bevakningar med fynd från morgonkörningen.
function byggVy() {
  if (!konto.inloggad) { V.spar = D.spar; V.poster = D.poster; V.egna = new Set(); }
  else {
    const f = konto.fynd || { spar: [], poster: [] };
    const egnaSpar = konto.profiler.map(p => {
      const id = "p" + p.id, fran = (f.spar || []).find(s => s.id === id);
      return { id, namn: p.namn, kategorier: fran ? fran.kategorier : Object.keys(p.sokningar || {}) };
    });
    V.egna = new Set(egnaSpar.map(s => s.id));
    V.spar = (konto.admin ? D.spar : []).concat(egnaSpar);
    V.poster = (konto.admin ? D.poster : []).concat((f.poster || []).filter(p => V.egna.has(p.spar)));
    if (!konto.admin && f.uppdaterad) $("upd").textContent = f.uppdaterad;
  }
  if (!V.spar.some(s => s.id === st.spar)) { st.spar = (V.spar[0] || {}).id; st.cat = ""; }
  byggFilter(); renderTabs(); renderChips(); render();
}

// ── Mina bevakningar ────────────────────────────────────────────────
function sokTillText(sok) {
  return Object.entries(sok || {}).map(([k, l]) => k + ":\n" + l.join("\n")).join("\n\n");
}
function textTillSok(text) {
  const ut = {}; let kat = "Sökningar";
  for (let rad of text.split("\n")) {
    rad = rad.replace(/^[\s•*-]+/, "").trim();
    if (!rad) continue;
    if (rad.endsWith(":")) { kat = rad.slice(0, -1).trim().slice(0, 40) || "Sökningar"; continue; }
    (ut[kat] = ut[kat] || []);
    if (!ut[kat].some(q => q.toLowerCase() === rad.toLowerCase())) ut[kat].push(rad.slice(0, 60));
  }
  for (const k of Object.keys(ut)) if (!ut[k].length) delete ut[k];
  return ut;
}
function antalSok(sok) { return Object.values(sok).reduce((n, l) => n + l.length, 0); }

function profilkort(p) {
  const kort = document.createElement("form"); kort.className = "profilkort"; kort.noValidate = true;
  const uid = "pk" + (p.id || ("ny" + Math.random().toString(36).slice(2, 7)));
  kort.innerHTML = `
    <label class="rubr" for="${uid}-namn">Namn på bevakningen</label>
    <input type="text" id="${uid}-namn" maxlength="40" placeholder="t.ex. Sommarhuset eller Glassamlingen">
    <label class="rubr" for="${uid}-beskr">Vad letar du efter? <small>Stil, färger, material, epoker, formgivare – med egna ord</small></label>
    <textarea id="${uid}-beskr" rows="6" maxlength="6000" placeholder="t.ex. Ett ljust 50-talshus. Jag gillar svensk design från 1940–70: teak, mässing, Josef Frank-tyger, Gustavsbergs keramik och färgat glas. Gärna lampor och små sidobord."></textarea>
    <div class="falt"><label class="knapp" for="${uid}-fil">📄 Läs in en textfil</label><input class="fil" type="file" id="${uid}-fil" accept=".md,.txt,text/plain,text/markdown"></div>
    <label class="rubr" for="${uid}-har">Har redan eller vill inte ha <small>en sak per rad</small></label>
    <textarea id="${uid}-har" rows="3" maxlength="1500" placeholder="t.ex. matbord\nkristallkronor"></textarea>
    <label class="rubr" for="${uid}-pris">Högsta pris (kr) <small>tomt = ingen gräns</small></label>
    <input type="number" id="${uid}-pris" min="0" step="100" inputmode="numeric">
    <label class="rubr" for="${uid}-sok">Sökord <small>en per rad · rader som slutar med kolon blir flikar · högst 30</small></label>
    <div class="falt"><button class="knapp" type="button" data-foresla>✨ Föreslå sökord</button></div>
    <p class="kommentar" data-kommentar hidden></p>
    <textarea id="${uid}-sok" rows="9" placeholder="Möbler:\nteak sidobord\nJosef Frank\n\nGlas:\nErik Höglund"></textarea>
    <div class="falt">
      <button class="knapp primar" type="submit">Spara</button>
      ${p.id ? '<button class="knapp" type="button" data-bort>Ta bort</button>' : ""}
    </div>
    <div class="status" role="status" data-status></div>`;
  const f = (id) => kort.querySelector("#" + uid + "-" + id);
  f("namn").value = p.namn || ""; f("beskr").value = p.beskrivning || ""; f("har").value = p.har_redan || "";
  f("pris").value = p.max_pris || ""; f("sok").value = sokTillText(p.sokningar);
  const status = (t) => kort.querySelector("[data-status]").textContent = t;

  f("fil").onchange = async (e) => {
    const fil = e.target.files[0]; if (!fil) return;
    if (fil.size > 200000) { status("Filen är för stor – klistra in det viktigaste i stället."); return; }
    const text = (await fil.text()).slice(0, 6000);
    f("beskr").value = f("beskr").value ? f("beskr").value + "\n\n" + text : text;
    status("Filen är inläst" + (text.length >= 6000 ? " (de första 6 000 tecknen)." : ".")); e.target.value = "";
  };
  kort.querySelector("[data-foresla]").onclick = async (e) => {
    if (f("beskr").value.trim().length < 10) { status("Skriv några rader om vad du letar efter först."); f("beskr").focus(); return; }
    e.target.disabled = true; status("Claude tänker ut sökord …");
    try {
      const { data, error } = await konto.sb.functions.invoke("fyndjakt-kann-igen", { body: {
        typ: "profil", namn: f("namn").value, beskrivning: f("beskr").value, har_redan: f("har").value } });
      if (error || !data || data.fel) throw new Error((data && data.fel) || "Kunde inte ta fram sökord just nu.");
      f("sok").value = sokTillText(data.sokningar);
      if (!f("namn").value && data.namn) f("namn").value = data.namn;
      const k = kort.querySelector("[data-kommentar]"); k.textContent = data.kommentar || ""; k.hidden = !data.kommentar;
      status("Klart – ändra fritt och tryck Spara.");
    } catch (x) { console.error(x); status(x.message); }
    finally { e.target.disabled = false; }
  };
  kort.onsubmit = async (e) => {
    e.preventDefault();
    const sokningar = textTillSok(f("sok").value);
    const rad = { namn: f("namn").value.trim().slice(0, 40), beskrivning: f("beskr").value.trim(), har_redan: f("har").value.trim(),
                  max_pris: f("pris").value ? Math.max(0, Math.round(+f("pris").value)) : null, sokningar,
                  uppdaterad: new Date().toISOString() };
    if (!rad.namn) { status("Ge bevakningen ett namn."); f("namn").focus(); return; }
    if (!antalSok(sokningar)) { status("Lägg till minst ett sökord – eller tryck ✨ Föreslå sökord."); return; }
    if (antalSok(sokningar) > 30) { status("Högst 30 sökord – ta bort " + (antalSok(sokningar) - 30) + "."); return; }
    status("Sparar …");
    const q = p.id ? konto.sb.from("fyndjakt_profiler").update(rad).eq("id", p.id)
                   : konto.sb.from("fyndjakt_profiler").insert(rad);
    const { data, error } = await q.select().single();
    if (error) { console.error(error); status("Kunde inte spara – försök igen."); return; }
    const i = konto.profiler.findIndex(x => x.id === data.id);
    if (i >= 0) konto.profiler[i] = data; else konto.profiler.push(data);
    konto.vald = "p" + data.id;
    byggVy(); renderProfiler();
    $("valkommen").hidden = true;
    const ny = $("prof-lista").querySelector('[data-id="' + data.id + '"] [data-status]');
    if (ny) ny.textContent = "Sparat! Appen letar efter det här från i morgon bitti.";
  };
  const bort = kort.querySelector("[data-bort]");
  if (bort) bort.onclick = async () => {
    if (bort.dataset.saker !== "1") { bort.dataset.saker = "1"; bort.textContent = "Tryck igen för att ta bort"; return; }
    const { error } = await konto.sb.from("fyndjakt_profiler").delete().eq("id", p.id);
    if (error) { status("Kunde inte ta bort – försök igen."); return; }
    konto.profiler = konto.profiler.filter(x => x.id !== p.id);
    konto.vald = null;
    byggVy(); renderProfiler();
  };
  if (p.id) kort.dataset.id = p.id;
  return kort;
}

// Listan överst: huvudspåren (styrs av filer), egna bevakningar och "+ Ny bevakning".
function renderProfiler() {
  const val = [];
  if (konto.admin) D.spar.forEach(sp => val.push({ v: "fil:" + sp.id, t: sp.namn + " (huvudspår)" }));
  konto.profiler.forEach(pr => val.push({ v: "p" + pr.id, t: pr.namn }));
  if (konto.profiler.length < 3) val.push({ v: "ny", t: "+ Ny bevakning" });
  if (!val.some(x => x.v === konto.vald)) konto.vald = (konto.profiler.length ? "p" + konto.profiler[0].id : val[0].v);
  $("prof-val").replaceChildren(...val.map(x => new Option(x.t, x.v)));
  $("prof-val").value = konto.vald;
  let kort;
  if (konto.vald === "ny") kort = profilkort({});
  else if (konto.vald.startsWith("fil:")) kort = filkort(D.spar.find(sp => "fil:" + sp.id === konto.vald));
  else kort = profilkort(konto.profiler.find(pr => "p" + pr.id === konto.vald));
  $("prof-lista").replaceChildren(kort);
}
$("prof-val").onchange = (e) => { konto.vald = e.target.value; renderProfiler(); };

function filkort(sp) {
  const d = document.createElement("div"); d.className = "profilkort filspar";
  const fil = sp.id === "hemmet" ? "stil.md" : sp.id === "samlingen" ? "samlingsprofil.md" : "config.yaml";
  d.innerHTML = '<p class="hj" style="margin:0">Det här spåret styrs av filen <b></b> och syns för alla som besöker sidan. ' +
    'Be Claude i chatten om du vill ändra stilen eller sökorden. Reaktioner och Min smak påverkar det precis som vanligt.</p>';
  d.querySelector("b").textContent = fil;
  for (const [kat, lista] of Object.entries(sp.sokningar || {})) {
    const k = document.createElement("div"); k.className = "kat"; k.textContent = kat; d.appendChild(k);
    const o = document.createElement("div"); o.className = "ord";
    lista.forEach(q => { const x = document.createElement("span"); x.textContent = q; o.appendChild(x); });
    d.appendChild(o);
  }
  return d;
}

function oppnaProfiler(valkommen) {
  $("valkommen").hidden = !valkommen;
  if (valkommen) konto.vald = "ny";
  renderProfiler(); oppna("p-prof");
  if (konto.admin) laddaMedlemmar();
  $("admin").hidden = !konto.admin;
}

async function laddaMedlemmar() {
  const { data, error } = await konto.sb.rpc("fyndjakt_medlemmar");
  if (error || !data) return;
  const rader = (data.medlemmar || []).map(m => {
    const li = document.createElement("li");
    li.innerHTML = '<div class="txt"><span class="etik"></span></div>';
    li.querySelector(".etik").textContent = m.admin ? "Administratör" : (m.profiler ? m.profiler + " bevakning" + (m.profiler > 1 ? "ar" : "") : "Inga bevakningar än");
    li.querySelector(".txt").append(m.epost || "");
    return li;
  }).concat((data.vantar || []).map(e => {
    const li = document.createElement("li");
    li.innerHTML = '<div class="txt"><span class="etik">Inbjuden – har inte loggat in än</span></div>';
    li.querySelector(".txt").append(e);
    return li;
  }));
  $("l-medlemmar").replaceChildren(...rader);
}
$("f-bjud").onsubmit = async (e) => {
  e.preventDefault();
  const epost = $("bjud-epost").value.trim(); if (!epost) return;
  visaStatus("bjud-status", "Bjuder in …");
  const { error } = await konto.sb.rpc("fyndjakt_bjud_in", { epost });
  if (error) { console.error(error); visaStatus("bjud-status", "Det gick inte – kolla adressen."); return; }
  $("bjud-epost").value = "";
  visaStatus("bjud-status", "Klart! Be " + epost + " gå in på sidan, trycka Logga in och använda den adressen.");
  laddaMedlemmar();
};

if (D.supabase && window.supabase) {
  konto.sb = window.supabase.createClient(D.supabase.url, D.supabase.nyckel);
  $("konto").hidden = false;
  $("b-logga").onclick = async () => {
    if (konto.inloggad) { await konto.sb.auth.signOut(); } else oppna("p-login");
  };
  $("b-smak").onclick = () => { sparVal($("a-spar"), st.spar); renderSmak(); oppna("p-smak"); };
  $("b-prof").onclick = () => oppnaProfiler(false);
  konto.sb.auth.onAuthStateChange((_ev, session) => { setTimeout(() => uppdateraKonto(session), 0); });
}

renderTabs(); renderChips(); render();
</script>
</body>
</html>
"""
