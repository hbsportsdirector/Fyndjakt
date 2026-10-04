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


def _ord(fras: str) -> list[str]:
    return [o for o in re.findall(r"[\wåäöéü]+", fras.lower()) if o not in SMAORD and len(o) > 1]


def relevant(titel: str, fras: str) -> bool:
    """Alla meningsfulla ord i sökfrasen måste finnas i titeln (ordstam räcker, t.ex. 'vas' ~ 'vaser')."""
    t = titel.lower()
    return all(o[:max(3, len(o) - 2)] in t for o in _ord(fras))


def salda(fras: str, sidor: int = 3, nu: float | None = None) -> list[int]:
    """Slutpriser (SEK) för sålda föremål som matchar sökfrasen."""
    nu = nu or time.time()
    gräns = nu - MAX_ALDER_AR * 365 * 86400
    priser = []
    for sida in range(1, sidor + 1):
        r = requests.get(API, params={"q": fras, "is": "ended", "per_page": 48, "page": sida},
                         headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        priser += tolka(data.get("items", []), fras, gräns)
        if sida >= (data.get("pagination") or {}).get("total_pages", 1):
            break
        time.sleep(1)
    return priser


def tolka(poster: list[dict], fras: str, gräns: float = 0) -> list[int]:
    ut = []
    for p in poster:
        if p.get("state") != "sold" or p.get("currency") != "SEK":
            continue
        pris = p.get("highest_bid") or max((b.get("amount", 0) for b in p.get("bids") or []), default=0)
        if not pris or (p.get("ends_at") or 0) < gräns:
            continue
        if relevant(p.get("title", ""), fras):
            ut.append(int(pris))
    return ut


def sammanfatta(priser: list[int]) -> dict | None:
    """Median och mittersta hälften (25–75 %). Kräver minst 3 försäljningar."""
    if len(priser) < 3:
        return None
    s = sorted(priser)
    kvart = statistics.quantiles(s, n=4) if len(s) >= 4 else [s[0], statistics.median(s), s[-1]]
    return {"median": round(statistics.median(s)), "lag": round(kvart[0]), "hog": round(kvart[2]), "antal": len(s)}


def jamfor(fras: str) -> dict | None:
    if not fras or not _ord(fras):
        return None
    return sammanfatta(salda(fras))
