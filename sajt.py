"""Bygger hemsidan (site/index.html) från databasen. Publiceras via GitHub Pages."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROT = Path(__file__).parent
UT = ROT / "site"

FALT = ["nyckel", "titel", "url", "betyg", "motivering", "kalla", "kategori",
        "pris", "pris_text", "plats", "slutar", "slutar_ts", "bilder", "sedd", "spar"]


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
        poster.append({k: r.get(k) for k in FALT})
    spar_cfg = cfg.get("spar") or {"": {"namn": "Fynd", "sokningar": cfg.get("sokningar", {})}}
    forsta = next(iter(spar_cfg))
    for p in poster:
        p["spar"] = p.get("spar") or forsta
    spar = [{"id": sid, "namn": s.get("namn", sid), "kategorier": list(s.get("sokningar", {}).keys())}
            for sid, s in spar_cfg.items()]
    nu = datetime.now(ZoneInfo("Europe/Stockholm")).strftime("%-d/%-m kl %H:%M")

    data = json.dumps(
        {"poster": poster, "spar": spar, "uppdaterad": nu,
         "standard": cfg.get("min_betyg", 7), "golv": min_betyg},
        ensure_ascii=False,
    ).replace("</", "<\\/")

    UT.mkdir(exist_ok=True)
    fil = UT / "index.html"
    fil.write_text(MALL.replace("__DATA__", data), encoding="utf-8")
    print(f"Hemsidan byggd: {len(poster)} fynd → {fil}")
    return fil


MALL = r"""<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Fyndjakt · The Reading Room</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
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
  header { padding: 40px 16px 8px; text-align: center; }
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
  .empty { text-align: center; color: var(--muted); padding: 60px 16px; font-family: "Cormorant Garamond", serif; font-size: 24px; font-style: italic; }
  footer { text-align: center; color: var(--muted); font-size: 13px; padding: 0 16px 40px; }
</style>
</head>
<body>
<header>
  <div class="ornament">✦ Fyndjakt ✦</div>
  <h1>Dagens <em>fynd</em></h1>
  <p class="sub">Utvalt från svenska auktioner och second hand · uppdaterad <span id="upd"></span></p>
</header>

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
      </select>
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
<footer>Bedömt av Claude mot dina profiler · Länkarna går till auktionen/annonsen</footer>

<script>
const D = __DATA__;
const st = { spar: (D.spar[0] || {}).id, cat: "", src: "", min: D.standard, sort: "betyg" };
const $ = (id) => document.getElementById(id);
const NU = Date.now() / 1000;
const KALLNAMN = { auctionet: "Auctionet", tradera: "Tradera", bukowskis: "Bukowskis", myrorna: "Myrorna", stadsmissionen: "Stadsmissionen" };
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
    n.textContent = D.poster.filter(p => p.spar === s.id && p.betyg >= st.min).length;
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
  mm("", p.plats);
  if (p.slutar) mm(p.slutar_ts && p.slutar_ts - NU < 86400 * 2 ? "soon" : "", "Slutar " + p.slutar);
  mm("", KALLNAMN[p.kalla] || p.kalla);
  b.appendChild(m); a.appendChild(b);
  return a;
}

function render() {
  let l = D.poster.filter(p =>
    p.spar === st.spar && (!st.cat || p.kategori === st.cat) && (!st.src || p.kalla === st.src) && p.betyg >= st.min);
  const s = {
    betyg: (a, b) => b.betyg - a.betyg || seddTs(b) - seddTs(a),
    ny: (a, b) => seddTs(b) - seddTs(a),
    slut: (a, b) => (a.slutar_ts || 9e12) - (b.slutar_ts || 9e12),
    pris: (a, b) => (a.pris ?? 9e12) - (b.pris ?? 9e12),
  }[st.sort];
  l.sort(s);
  $("grid").replaceChildren(...l.map(card));
  $("empty").hidden = l.length > 0;
  $("count").textContent = l.length + (l.length === 1 ? " fynd" : " fynd");
}

$("sort").onchange = e => { st.sort = e.target.value; render(); };
$("src").onchange = e => { st.src = e.target.value; render(); };
$("min").oninput = e => { st.min = +e.target.value; $("minv").textContent = st.min; renderTabs(); render(); };
renderTabs(); renderChips(); render();
</script>
</body>
</html>
"""
