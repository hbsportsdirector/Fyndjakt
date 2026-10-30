"""Prisjämförelse: vad har liknande föremål sålts för på Auctionet?
Använder Auctionets avslutade auktioner (is=ended) och räknar ut median och spann för sålda föremål."""
import re
import statistics
import time

import requests

API = "https://auctionet.com/api/v2/items.json"
HEADERS = {"User-Agent": "Fyndjakt/1.0 (privat bevakning)"}
MAX_ALDER_AR = 5
SMAORD = {"och", "med", "i", "av", "på", "för", "en", "ett", "the", "a"}
TALORD = {"två": 2, "tre": 3, "fyra": 4, "fem": 5, "sex": 6, "sju": 7, "åtta": 8, "nio": 9, "tio": 10,
          "elva": 11, "tolv": 12}


def _ord(fras: str) -> list[str]:
    return [o for o in re.findall(r"[\wåäöéü]+", fras.lower()) if o not in SMAORD and len(o) > 1]


def relevant(titel: str, fras: str) -> bool:
    """Alla meningsfulla ord i sökfrasen måste finnas i titeln (ordstam räcker, t.ex. 'vas' ~ 'vaser')."""
    t = titel.lower()
    return all(o[:max(3, len(o) - 2)] in t for o in _ord(fras))


def styck_i(titel: str) -> int:
    """Antal föremål som en auktionstitel säljer: "vaser, 2 st" → 2, "14 delar" → 14, "ett par" → 2, annars 1."""
    t = (titel or "").lower()
    m = re.search(r"\b(\d{1,3})\s*(?:st|st\.|stycken|delar|pcs)\b", t) or \
        re.search(r"\b(" + "|".join(TALORD) + r")\s+(?:st|stycken|delar)\b", t)
    if m:
        n = TALORD.get(m.group(1)) or int(m.group(1))
        return max(1, min(n, 100))
    return 2 if re.search(r"\b(?:ett\s+)?par\b", t) else 1


def salda(fras: str, sidor: int = 3, nu: float | None = None, uteslut: tuple = (),
          per_styck: bool = False) -> list[int]:
    """Slutpriser (SEK) för sålda föremål som matchar sökfrasen (och inte har något av orden i uteslut).
    per_styck: partier räknas om till pris per föremål ("vaser, 2 st" för 1 300 kr → 650 kr)."""
    nu = nu or time.time()
    gräns = nu - MAX_ALDER_AR * 365 * 86400
    priser = []
    for sida in range(1, sidor + 1):
        r = requests.get(API, params={"q": fras, "is": "ended", "per_page": 48, "page": sida},
                         headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        priser += tolka(data.get("items", []), fras, gräns, uteslut, per_styck)
        if sida >= (data.get("pagination") or {}).get("total_pages", 1):
            break
        time.sleep(1)
    return priser


def tolka(poster: list[dict], fras: str, gräns: float = 0, uteslut: tuple = (), per_styck: bool = False) -> list[int]:
    ut = []
    for p in poster:
        if p.get("state") != "sold" or p.get("currency") != "SEK":
            continue
        pris = p.get("highest_bid") or max((b.get("amount", 0) for b in p.get("bids") or []), default=0)
        if not pris or (p.get("ends_at") or 0) < gräns:
            continue
        titel = (p.get("title") or "").lower()
        if relevant(titel, fras) and not any(o in titel for o in uteslut):
            ut.append(round(pris / styck_i(titel)) if per_styck else int(pris))
    return ut


def _ren_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def avslutade_ur(poster: list[dict], fras: str, gräns: float = 0) -> list[dict]:
    """Avslutade auktioner (sålda och osålda) som matchar sökfrasen: [{pris, sald, titel, text, slutade}].
    pris är klubbat pris för sålda, 0 för osålda. text = titel + beskrivning (för att läsa av mått)."""
    ut = []
    for p in poster:
        if p.get("currency") != "SEK" or (p.get("ends_at") or 0) < gräns:
            continue
        titel = (p.get("title") or "").strip()
        if not relevant(titel.lower(), fras):
            continue
        sald = p.get("state") == "sold"
        pris = (p.get("highest_bid") or max((b.get("amount", 0) for b in p.get("bids") or []), default=0)) if sald else 0
        if sald and not pris:
            continue
        ut.append({"pris": int(pris), "sald": sald, "titel": titel, "slutade": p.get("ends_at"),
                   "text": titel + " " + _ren_text(p.get("description", "")) + " " + _ren_text(p.get("condition", ""))})
    return ut


def avslutade(fras: str, sidor: int = 3, nu: float | None = None) -> list[dict]:
    """Som salda(), men med osålda och beskrivningar – för omvärderingen av samlingen (vardering.py)."""
    nu = nu or time.time()
    gräns = nu - MAX_ALDER_AR * 365 * 86400
    ut = []
    for sida in range(1, sidor + 1):
        r = requests.get(API, params={"q": fras, "is": "ended", "per_page": 48, "page": sida},
                         headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        ut += avslutade_ur(data.get("items", []), fras, gräns)
        if sida >= (data.get("pagination") or {}).get("total_pages", 1):
            break
        time.sleep(1)
    return ut


def sammanfatta(priser: list[int]) -> dict | None:
    """Median och mittersta hälften (25–75 %). Kräver minst 3 försäljningar."""
    if len(priser) < 3:
        return None
    s = sorted(priser)
    kvart = statistics.quantiles(s, n=4) if len(s) >= 4 else [s[0], statistics.median(s), s[-1]]
    return {"median": round(statistics.median(s)), "lag": round(kvart[0]), "hog": round(kvart[2]), "antal": len(s)}


def jamfor(fras: str, uteslut: tuple = (), per_styck: bool = False) -> dict | None:
    if not fras or not _ord(fras):
        return None
    return sammanfatta(salda(fras, uteslut=uteslut, per_styck=per_styck))
