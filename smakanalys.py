"""Smakanalys: Claude jämför det kunden gillat med det hen ogillat – bilder, titlar och tidigare bedömningar –
och skriver ner vilka egenskaper som skiljer dem åt. Kunden behöver inte förklara sig.

Resultatet ("lärdomar") läggs in i spårets profil inför bedömningen och visas i appen under Min smak.
Analysen görs bara om när reaktionerna har ändrats, och sparas i data/smakanalys.json.
"""
import hashlib
import json
from pathlib import Path

FIL = Path(__file__).parent / "data" / "smakanalys.json"
MODELL = "claude-sonnet-5-5"
MIN_REAKTIONER = 3
MAX_PER_SIDA = 12

INSTRUKTION = """Du hjälper en app som letar begagnade fynd åt en kund. Nedan finns föremål kunden har reagerat på:
👍 = gillade, 👎 = gillade inte, 🛒 = köpte. Till varje föremål finns titeln, din tidigare bedömning och ofta en bild.

Jämför noga, främst bilderna: vilka EGENSKAPER skiljer det kunden gillar från det hen inte gillar?
Tänk på färg, form, epok, material, motiv, ytbehandling, storlek, prisnivå och skick.
Var extra uppmärksam när samma formgivare, konstnär eller tillverkare finns på båda sidor – vad skiljer då
föremålen åt? Det är ofta det viktigaste att förstå.

Skriv 3–8 korta, konkreta punkter på svenska, formulerade som regler för kommande bedömningar, t.ex.
"Gillar Erik Höglund i klara blå och gröna färger – inte de bruna/bärnstensfärgade."
Hitta inte på mönster som inte syns i underlaget; finns för lite att gå på, skriv färre punkter.
Om kunden själv skrivit en förklaring väger den tyngst.
Svara ENBART med punkterna, en per rad, som börjar med "- "."""


def _las() -> dict:
    try:
        return json.loads(FIL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _nyckel(reakt: list[dict]) -> str:
    delar = sorted(f"{r.get('nyckel')}|{r.get('typ')}|{r.get('kommentar') or ''}" for r in reakt)
    return hashlib.sha256("\n".join(delar).encode()).hexdigest()[:16]


def _innehall(reakt: list[dict]) -> list[dict]:
    """Bild + text per föremål, gillade först. Högst MAX_PER_SIDA av varje sort (de senaste)."""
    ut = []
    for typ, tecken in (("gillar", "👍"), ("kopt", "🛒"), ("ogillar", "👎")):
        for r in [r for r in reakt if r.get("typ") == typ][:MAX_PER_SIDA]:
            rad = f"{tecken} {r.get('titel', '')}"
            if r.get("pris_text"):
                rad += f" · {r['pris_text']}"
            if r.get("motivering"):
                rad += f"\n   Din bedömning då: {r['motivering'][:200]}"
            if r.get("kommentar"):
                rad += f'\n   Kundens egen förklaring: "{r["kommentar"]}"'
            if r.get("bild"):
                ut.append({"type": "image", "source": {"type": "url", "url": r["bild"]}})
            ut.append({"type": "text", "text": rad})
    return ut


def _fraga(klient, reakt: list[dict]) -> str:
    import anthropic
    innehall = _innehall(reakt)
    try:
        svar = klient.messages.create(model=MODELL, max_tokens=700, system=INSTRUKTION,
                                      messages=[{"role": "user", "content": innehall}])
    except anthropic.BadRequestError:  # t.ex. en bild som inte längre finns – försök med bara text
        svar = klient.messages.create(model=MODELL, max_tokens=700, system=INSTRUKTION,
                                      messages=[{"role": "user", "content": [d for d in innehall if d["type"] == "text"]}])
    text = "".join(b.text for b in svar.content if getattr(b, "type", "text") == "text")
    rader = [r.strip() for r in text.splitlines() if r.strip().startswith(("-", "•"))]
    return "\n".join("- " + r.lstrip("-• ").strip() for r in rader[:10])


def analysera(cfg: dict, export: dict | None, klient=None) -> dict:
    """Lägger till lärdomar i varje spårs profil (spar["lardomar"]). Utan klient används bara sparade analyser."""
    if not export:
        return {}
    import smak
    cache = _las()
    nya = 0
    for sid, spar in cfg["spar"].items():
        agare = smak._agare(spar, export)
        reakt = [r for r in export.get("reaktioner", []) if smak._galler(r, sid, agare) and r.get("titel")]
        if len(reakt) < MIN_REAKTIONER or not any(r["typ"] == "gillar" for r in reakt):
            continue
        nyckel = _nyckel(reakt)
        post = cache.get(sid)
        if (not post or post.get("nyckel") != nyckel) and klient is not None:
            try:
                lardomar = _fraga(klient, reakt)
                if lardomar:
                    post = cache[sid] = {"nyckel": nyckel, "lardomar": lardomar, "antal": len(reakt)}
                    nya += 1
            except Exception as e:  # analysen får aldrig stoppa körningen
                print(f"  Smakanalys misslyckades för {spar.get('namn')}: {e}")
        if post and post.get("lardomar"):
            spar["lardomar"] = post["lardomar"]
            spar["profil"] += ("\n\nLÄRDOMAR FRÅN KUNDENS REAKTIONER – det här har du själv sett när du jämfört det kunden "
                               "gillat med det hen inte gillat. Följ det:\n" + post["lardomar"])
    if nya:
        FIL.parent.mkdir(exist_ok=True)
        FIL.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Smakanalys: {nya} nya analyser.")
    return {"nya": nya}
