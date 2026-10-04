"""Lärande: hämtar dina reaktioner (gillar / inte min stil / köpt) och anteckningar från Supabase
och väver in dem i profilen och sökningarna inför varje körning."""
import os

import requests

MAX_EXEMPEL = 20


def hamta(cfg: dict) -> dict | None:
    """Hämtar alla användares reaktioner och anteckningar. Kräver FYNDJAKT_BOT_TOKEN."""
    sb = cfg.get("supabase") or {}
    token = os.getenv("FYNDJAKT_BOT_TOKEN")
    if not (sb.get("url") and sb.get("nyckel") and token):
        print("Min smak: ingen koppling till databasen (FYNDJAKT_BOT_TOKEN saknas) – hoppar över lärandet.")
        return None
    r = requests.post(
        f"{sb['url']}/rest/v1/rpc/fyndjakt_export",
        json={"token": token},
        headers={"apikey": sb["nyckel"], "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _galler(rad: dict, sid: str) -> bool:
    return not rad.get("spar") or rad.get("spar") == sid


def profiltillagg(export: dict, sid: str) -> str:
    """Text som läggs till i spårets profil."""
    reakt = [r for r in export.get("reaktioner", []) if _galler(r, sid)]
    ant = [a for a in export.get("anteckningar", []) if _galler(a, sid)]
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


def extra_sokningar(export: dict, sid: str) -> list[str]:
    """Sökfraser från saker kunden fotat eller skrivit att hen gillar."""
    ut = []
    for a in export.get("anteckningar", []):
        if a["typ"] == "gillar" and a.get("sokord") and _galler(a, sid):
            fras = a["sokord"].strip()
            if fras and fras.lower() not in (x.lower() for x in ut):
                ut.append(fras)
    return ut[:25]


def tillampa(cfg: dict, export: dict | None) -> None:
    """Uppdaterar varje spårs profil och sökningar på plats."""
    if not export:
        return
    for sid, spar in cfg["spar"].items():
        tillagg = profiltillagg(export, sid)
        if tillagg:
            spar["profil"] = spar["profil"] + "\n\n" + tillagg
        befintliga = {q.lower() for qs in spar["sokningar"].values() for q in qs}
        nya = [q for q in extra_sokningar(export, sid) if q.lower() not in befintliga]
        if nya:
            spar["sokningar"]["Från Min smak"] = nya
    antal = len(export.get("reaktioner", [])), len(export.get("anteckningar", []))
    print(f"Min smak: {antal[0]} reaktioner och {antal[1]} anteckningar inlästa.")
