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


def bygg(db, cfg: dict) -> Path:
    min_betyg = cfg.get("sajt_min_betyg", 6)
    max_per = cfg.get("sajt_max_per_sokord") or 0
    per_sokord: dict[str, int] = {}
    poster = []
    for r in db.traffar(min_betyg):  # redan sorterade bäst först
        nyckel = r.get("sokord") or r.get("nyckel")
        if max_per and per_sokord.get(nyckel, 0) >= max_per:
            continue
        per_sokord[nyckel] = per_sokord.get(nyckel, 0) + 1
        post = {k: r.get(k) for k in FALT}
        post["ort"], post["region"] = region_for(r.get("kalla"), r.get("plats"))
        poster.append(post)
    spar_cfg = cfg.get("spar") or {"": {"namn": "Fynd", "sokningar": cfg.get("sokningar", {})}}
    forsta = next(iter(spar_cfg))
    for p in poster:
        p["spar"] = p.get("spar") or forsta
    spar = [{"id": sid, "namn": s.get("namn", sid), "kategorier": list(s.get("sokningar", {}).keys())}
            for sid, s in spar_cfg.items()]
    nu = datetime.now(ZoneInfo("Europe/Stockholm")).strftime("%-d/%-m kl %H:%M")

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
  .tolkning b { font-family: "Cormorant Garamond", Georgia, serif; font-size: 20px; display: block; margin-bottom: 4px; }
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
  @media (max-width: 560px) { .konto { position: static; justify-content: center; margin-bottom: 10px; } }
</style>
</head>
<body>
<header>
  <div class="konto" id="konto" hidden>
    <button class="knapp" id="b-smak" type="button" hidden>Min smak</button>
    <button class="knapp" id="b-logga" type="button">Logga in</button>
  </div>
  <div class="ornament">✦ Fyndjakt ✦</div>
  <h1>Dagens <em>fynd</em></h1>
  <p class="sub">Utvalt från svenska auktioner och second hand · uppdaterad <span id="upd"></span></p>
</header>

<p class="ingen-profil" id="ingen-profil" hidden>Du är inloggad men har ingen Fyndjakt-profil än. Be den som bjöd in dig att lägga till dig.</p>
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
    <p class="hj">Du får en inloggningslänk till din e-post. Inget lösenord behövs.</p>
    <form class="falt" id="f-login">
      <input type="email" id="login-epost" required placeholder="din@epost.se" autocomplete="email">
      <button class="knapp primar" type="submit">Skicka länk</button>
    </form>
    <div class="status" id="login-status" role="status"></div>
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
      <img class="forhand" id="foto-forhand" alt="Ditt foto" hidden>
      <div class="status" id="foto-status" role="status"></div>
      <div class="tolkning" id="tolkning" hidden>
        <b id="t-beskr"></b>
        <div class="samtal" id="t-samtal" aria-live="polite"></div>
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
const st = { spar: (D.spar[0] || {}).id, cat: "", src: "", reg: "", min: D.standard, sort: "betyg" };
try { st.reg = localStorage.getItem("fyndjakt-omrade") || ""; } catch (e) {}
const $ = (id) => document.getElementById(id);
const NU = Date.now() / 1000;
const KALLNAMN = { auctionet: "Auctionet", tradera: "Tradera", bukowskis: "Bukowskis", myrorna: "Myrorna", stadsmissionen: "Stadsmissionen" };
const REGORDNING = ["Stockholm", "Uppsala och Mälardalen", "Östergötland, Småland och Blekinge", "Västsverige och Värmland",
  "Skåne", "Norrland och Dalarna", "Övriga Sverige", "Okänd ort"];
const finns = new Set(D.poster.map(p => p.region));
REGORDNING.filter(r => finns.has(r)).forEach(r => {
  const o = document.createElement("option"); o.value = r; o.textContent = r; $("reg").appendChild(o);
});
if (st.reg && !finns.has(st.reg)) st.reg = "";
$("reg").value = st.reg;
[...new Set(D.poster.map(p => p.kalla))].sort().forEach(k => {
  const o = document.createElement("option"); o.value = k; o.textContent = KALLNAMN[k] || k; $("src").appendChild(o);
});

$("upd").textContent = D.uppdaterad;
$("min").min = D.golv; $("min").value = st.min; $("minv").textContent = st.min;

function chip(label, value) {
  const b = document.createElement("button");
  b.className = "chip"; b.textContent = label; b.type = "button";
  b.setAttribute("aria-pressed", String(st.cat === value));
  b.onclick = () => { st.cat = value; renderChips(); render(); };
  return b;
}
function aktivtSpar() { return D.spar.find(s => s.id === st.spar) || { kategorier: [] }; }
function renderTabs() {
  const t = $("tabs"); t.hidden = D.spar.length < 2;
  t.replaceChildren(...D.spar.map(s => {
    const b = document.createElement("button");
    b.className = "tab"; b.type = "button"; b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(s.id === st.spar));
    b.textContent = s.namn;
    const n = document.createElement("span"); n.className = "n";
    n.textContent = D.poster.filter(p => p.spar === s.id && p.betyg >= st.min && (!st.reg || p.region === st.reg)).length;
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
  let l = D.poster.filter(p =>
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
const konto = { sb: null, inloggad: false, reakt: new Map(), anteckningar: [] };
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
  select.replaceChildren(new Option("Alla flikar", ""), ...D.spar.map(s => new Option(s.namn, s.id)));
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
  const sparNamn = id => (D.spar.find(s => s.id === id) || {}).namn || "Alla flikar";
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
let fotoData = null;
let samtal = [];  // [{roll: "anvandare"|"claude", text}]

function visaTolkning(svar) {
  senasteTolkning = svar;
  $("t-beskr").textContent = svar.beskrivning + (svar.sakerhet === "låg" ? " (osäker)" : "");
  $("t-sok").value = svar.sokord || "";
  $("tolkning").hidden = false;
}
function visaSamtal() {
  $("t-samtal").replaceChildren(...samtal.filter(s => s.visa).map(s => {
    const p = document.createElement("p"); p.className = s.roll === "claude" ? "claude" : "du"; p.textContent = s.visa; return p;
  }));
}
async function fragaClaude(body) {
  const { data: svar, error } = await konto.sb.functions.invoke("fyndjakt-kann-igen", { body });
  if (error || !svar || svar.fel) {
    let txt = (svar && svar.fel) || "";
    try { if (!txt && error && error.context) txt = (await error.context.json()).fel; } catch (x) {}
    throw new Error(txt || "Kunde inte känna igen bilden just nu.");
  }
  return svar;
}
$("foto").onchange = async (e) => {
  const fil = e.target.files[0]; if (!fil) return;
  $("tolkning").hidden = true; visaStatus("foto-status", "Claude tittar på bilden …");
  try {
    const data = await skalaNer(fil);
    $("foto-forhand").src = data; $("foto-forhand").hidden = false;
    fotoData = data; samtal = [];
    const svar = await fragaClaude({ bild: data, mediatyp: "image/jpeg" });
    samtal.push({ roll: "claude", text: JSON.stringify(svar) });
    visaSamtal(); visaTolkning(svar);
    sparVal($("t-spar"), st.spar);
    visaStatus("foto-status", "");

  } catch (x) { console.error(x); visaStatus("foto-status", x.message || "Kunde inte läsa bilden."); }
  finally { e.target.value = ""; }
};
$("f-samtal").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("t-meddelande").value.trim();
  if (!text || !fotoData) return;
  samtal.push({ roll: "anvandare", text, visa: text });
  $("t-meddelande").value = ""; visaSamtal();
  visaStatus("foto-status", "Claude funderar …");
  try {
    const svar = await fragaClaude({ bild: fotoData, mediatyp: "image/jpeg", samtal: samtal.map(s => ({ roll: s.roll, text: s.text })) });
    samtal.push({ roll: "claude", text: JSON.stringify(svar), visa: svar.svar || "" });
    visaSamtal(); visaTolkning(svar); visaStatus("foto-status", "");
  } catch (x) { visaStatus("foto-status", x.message); }
};
document.querySelectorAll("[data-spara]").forEach(b => b.onclick = async () => {
  if (!senasteTolkning) return;
  const sok = $("t-sok").value.trim();
  const text = (senasteTolkning.beskrivning || "").trim() || sok || "Fotat föremål";
  const ok = await sparaAnteckning(b.dataset.spara, text, $("t-spar").value, sok);
  if (ok) {
    $("tolkning").hidden = true; $("foto-forhand").hidden = true; senasteTolkning = null; fotoData = null; samtal = []; visaSamtal();
    visaStatus("foto-status", b.dataset.spara === "gillar" ? "Sparat! Appen letar efter liknande från i morgon." : "Sparat!");
  }
});

$("f-login").onsubmit = async (e) => {
  e.preventDefault();
  visaStatus("login-status", "Skickar …");
  const { error } = await konto.sb.auth.signInWithOtp({
    email: $("login-epost").value.trim(),
    options: { emailRedirectTo: location.origin + location.pathname, shouldCreateUser: false },
  });
  visaStatus("login-status", error ? "Det gick inte – är det rätt e-post?" : "Klart! Öppna länken i mejlet på den här enheten.");
};

async function uppdateraKonto(session) {
  konto.inloggad = !!session;
  $("b-logga").textContent = session ? "Logga ut" : "Logga in";
  $("b-smak").hidden = !session;
  if (session) {
    const { data: medlem } = await konto.sb.rpc("fyndjakt_ar_medlem");
    if (!medlem) { konto.inloggad = false; $("b-smak").hidden = true; $("ingen-profil").hidden = false; }
    else await laddaMittData();
  } else { konto.reakt = new Map(); konto.anteckningar = []; $("ingen-profil").hidden = true; }
  renderTabs(); render();
}

if (D.supabase && window.supabase) {
  konto.sb = window.supabase.createClient(D.supabase.url, D.supabase.nyckel);
  $("konto").hidden = false;
  $("b-logga").onclick = async () => {
    if (konto.inloggad) { await konto.sb.auth.signOut(); } else oppna("p-login");
  };
  $("b-smak").onclick = () => { sparVal($("a-spar"), st.spar); renderSmak(); oppna("p-smak"); };
  konto.sb.auth.onAuthStateChange((_ev, session) => { setTimeout(() => uppdateraKonto(session), 0); });
}

renderTabs(); renderChips(); render();
</script>
</body>
</html>
"""
