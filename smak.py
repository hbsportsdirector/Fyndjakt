"""Användare och lärande.

Hämtar från Supabase:
- användarnas egna profiler (spår) som de skapat på hemsidan,
- deras reaktioner (gillar / inte min stil / köpt) och anteckningar i Min smak,
och väver in dem i spåren inför varje körning. Efter körningen läggs varje användares fynd upp igen.

Spåren i config.yaml tillhör administratören (Per) och visas publikt på hemsidan.
Användarnas egna spår syns bara för dem själva när de är inloggade.
"""
import os
import re

import requests

MAX_EXEMPEL = 20
MAX_SOKNINGAR_PER_PROFIL = 30
MAX_KATEGORIER = 8


def _anslutning(cfg: dict) -> tuple[str, str, str] | None:
    sb = cfg.get("supabase") or {}
    token = os.getenv("FYNDJAKT_BOT_TOKEN")
    if not (sb.get("url") and sb.get("nyckel") and token):
        return None
    return sb["url"], sb["nyckel"], token


def hamta(cfg: dict) -> dict | None:
    """Hämtar användare, profiler, reaktioner och anteckningar. Kräver FYNDJAKT_BOT_TOKEN."""
    ans = _anslutning(cfg)
    if not ans:
        print("Min smak: ingen koppling till databasen (FYNDJAKT_BOT_TOKEN saknas) – hoppar över lärandet.")
        return None
    url, nyckel, token = ans
    r = requests.post(f"{url}/rest/v1/rpc/fyndjakt_export", json={"token": token},
                      headers={"apikey": nyckel, "Content-Type": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()


def publicera(cfg: dict, fynd: dict) -> None:
    """Lägger upp varje användares fynd: {user_id: {"spar": [...], "poster": [...], ...}}."""
    ans = _anslutning(cfg)
    if not ans or not fynd:
        return
    url, nyckel, token = ans
    r = requests.post(f"{url}/rest/v1/rpc/fyndjakt_publicera", json={"token": token, "fynd": fynd},
                      headers={"apikey": nyckel, "Content-Type": "application/json"}, timeout=60)
    r.raise_for_status()
    print(f"Egna fynd upplagda för {r.json()} användare.")


def admins(export: dict | None) -> set[str]:
    return {u["user_id"] for u in (export or {}).get("anvandare", []) if u.get("admin")}


# ── Användarnas egna profiler → spår ────────────────────────────────

def _rensa_fras(q) -> str:
    q = re.sub(r"\s+", " ", str(q or "")).strip()
    return q[:60]


def rensa_sokningar(sokningar) -> dict[str, list[str]]:
    """Gör användarens sökningar säkra: rimliga längder och högst MAX_SOKNINGAR_PER_PROFIL totalt."""
    ut: dict[str, list[str]] = {}
    antal = 0
    if not isinstance(sokningar, dict):
        return ut
    for kat, fragor in list(sokningar.items())[:MAX_KATEGORIER]:
        kat = _rensa_fras(kat)[:40] or "Övrigt"
        if not isinstance(fragor, list):
            continue
        for q in fragor:
            q = _rensa_fras(q)
            if len(q) < 2 or antal >= MAX_SOKNINGAR_PER_PROFIL:
                continue
            if q.lower() in (x.lower() for x in ut.get(kat, [])):
                continue
            ut.setdefault(kat, []).append(q)
            antal += 1
    return ut


def profiltext(p: dict) -> str:
    delar = [
        "Kunden letar begagnade och vintage-föremål i Sverige. Så här beskriver kunden sin stil och vad hen söker:",
        (p.get("beskrivning") or "").strip() or f"(Ingen beskrivning – utgå från spårets namn: {p.get('namn')})",
    ]
    har = [r.strip(" -•\t") for r in (p.get("har_redan") or "").splitlines() if r.strip(" -•\t")]
    if har:
        delar.append("Kunden HAR REDAN följande – ge 0–3 åt samma typ av föremål:\n- " + "\n- ".join(har[:30]))
    return "\n\n".join(delar)


def lagg_till_profiler(cfg: dict, export: dict | None) -> int:
    """Lägger in medlemmarnas egna profiler som spår i cfg["spar"]."""
    if not export:
        return 0
    medlemmar = {u["user_id"] for u in export.get("anvandare", [])}
    n = 0
    for p in export.get("profiler", []):
        if p.get("user_id") not in medlemmar:
            continue
        sokningar = rensa_sokningar(p.get("sokningar"))
        if not sokningar:
            continue  # inget att leta efter än
        sid = f"p{p['id']}"
        spar = {
            "namn": (p.get("namn") or "Min jakt")[:40],
            "agare": p["user_id"],
            "publik": False,
            "sokningar": sokningar,
            "sidor": 2,
            "profil": profiltext(p),
            "uteslut_ord": [],
        }
        if p.get("max_pris"):
            spar["max_pris"] = int(p["max_pris"])
        cfg["spar"][sid] = spar
        n += 1
    if n:
        print(f"Användarprofiler: {n} egna spår inlästa.")
    return n


# ── Lärande ─────────────────────────────────────────────────────────

def _galler(rad: dict, sid: str, agare: set[str]) -> bool:
    """Gäller raden för spåret? Bara ägarens egna rader, och bara för rätt spår (eller alla spår)."""
    if agare and rad.get("user_id") and rad["user_id"] not in agare:
        return False
    return not rad.get("spar") or rad.get("spar") == sid


def _agare(spar: dict, export: dict) -> set[str]:
    return {spar["agare"]} if spar.get("agare") else admins(export)


def profiltillagg(export: dict, sid: str, agare: set[str] | None = None) -> str:
    """Text som läggs till i spårets profil."""
    agare = agare or set()
    reakt = [r for r in export.get("reaktioner", []) if _galler(r, sid, agare)]
    ant = [a for a in export.get("anteckningar", []) if _galler(a, sid, agare)]
    if not reakt and not ant:
        return ""

    def lista(rubrik: str, rader: list[str]) -> str:
        return f"{rubrik}\n" + "\n".join(f"- {x}" for x in rader[:MAX_EXEMPEL]) if rader else ""

    gillar = [r["titel"] for r in reakt if r["typ"] == "gillar" and r.get("titel")]
    ogillar = [r["titel"] for r in reakt if r["typ"] == "ogillar" and r.get("titel")]
    kopt = [r["titel"] for r in reakt if r["typ"] == "kopt" and r.get("titel")]
    a_gillar = [a["text"] for a in ant if a["typ"] == "gillar"]
    a_ogillar = [a["text"] for a in ant if a["typ"] == "ogillar"]
    a_har = [a["text"] for a in ant if a["typ"] == "har"]

    delar = [
        "KUNDENS EGNA REAKTIONER – väg in dem tungt. De säger mer än stilbeskrivningen.",
        lista("Fynd kunden gillat (ge liknande högt betyg):", gillar),
        lista("Kunden har själv sagt att hen gillar:", a_gillar),
        lista("Fynd kunden INTE tyckte passade (ge liknande lågt betyg):", ogillar),
        lista("Kunden vill INTE ha:", a_ogillar),
        lista("Kunden har redan köpt eller äger (ge 0–3 åt samma sak, men kompletterande föremål är bra):",
              kopt + a_har),
    ]
    return "\n\n".join(d for d in delar if d)


def extra_sokningar(export: dict, sid: str, agare: set[str] | None = None) -> list[str]:
    """Sökfraser från saker kunden fotat eller skrivit att hen gillar."""
    ut = []
    for a in export.get("anteckningar", []):
        if a["typ"] == "gillar" and a.get("sokord") and _galler(a, sid, agare or set()):
            fras = _rensa_fras(a["sokord"])
            if fras and fras.lower() not in (x.lower() for x in ut):
                ut.append(fras)
    return ut[:25]


def tillampa(cfg: dict, export: dict | None) -> None:
    """Lägger in användarnas profiler och uppdaterar varje spårs profil och sökningar på plats."""
    if not export:
        return
    cfg["_admins"] = admins(export)  # huvudspårens fynd läggs upp till dem
    lagg_till_profiler(cfg, export)
    for sid, spar in cfg["spar"].items():
        agare = _agare(spar, export)
        tillagg = profiltillagg(export, sid, agare)
        if tillagg:
            spar["profil"] = spar["profil"] + "\n\n" + tillagg
        befintliga = {q.lower() for qs in spar["sokningar"].values() for q in qs}
        nya = [q for q in extra_sokningar(export, sid, agare) if q.lower() not in befintliga]
        if nya:
            spar["sokningar"]["Från Min smak"] = nya[:15] if spar.get("agare") else nya
    antal = len(export.get("reaktioner", [])), len(export.get("anteckningar", []))
    print(f"Min smak: {antal[0]} reaktioner och {antal[1]} anteckningar inlästa.")
