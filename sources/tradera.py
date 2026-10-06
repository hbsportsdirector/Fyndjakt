"""Tradera – via Traderas officiella REST-API (v4).
Kräver gratis utvecklarnyckel: https://api.tradera.com/register
Sätt miljövariablerna TRADERA_APP_ID och TRADERA_APP_KEY."""
import os
import time
from datetime import datetime, timezone

import requests

from . import Annons

API = "https://api.tradera.com/v4/search"


def aktiverad() -> bool:
    return bool(os.getenv("TRADERA_APP_ID") and os.getenv("TRADERA_APP_KEY"))


def _hamta(d: dict, *namn, default=None):
    """API:et är i beta – tål både camelCase och PascalCase."""
    for n in namn:
        for variant in (n, n[0].upper() + n[1:]):
            if d.get(variant) not in (None, ""):
                return d[variant]
    return default


def tolka(post: dict, kategori: str = "") -> Annons | None:
    item_id = _hamta(post, "id")
    if not item_id:
        return None
    kop_nu = _hamta(post, "buyItNowPrice", default=0) or 0
    bud = _hamta(post, "maxBid", default=0) or 0
    nasta = _hamta(post, "nextBid", default=0) or 0
    har_bud = bool(_hamta(post, "hasBids", default=False)) or (_hamta(post, "bidCount", default=0) or 0) > 0

    if _hamta(post, "itemType") == "PureBuyItNow" or (kop_nu and not har_bud):
        pris = kop_nu or nasta or None
        pris_text = f"Köp nu {pris} kr" if pris else ""
        if kop_nu and _hamta(post, "itemType") != "PureBuyItNow":
            pris_text = f"Utrop {nasta} kr (köp nu {kop_nu} kr)"
            pris = nasta or kop_nu
    elif har_bud:
        pris, pris_text = bud, f"Bud {bud} kr" + (f" (köp nu {kop_nu} kr)" if kop_nu else "")
    else:
        pris, pris_text = nasta or None, f"Utrop {nasta} kr" if nasta else ""

    # Bilderna kommer i flera storlekar – ta den stora ("normal"), annars galleribilden.
    bilder = []
    for b in _hamta(post, "imageLinks", "detailedImageLinks", default=[]) or []:
        if isinstance(b, str):
            bilder.append(b)
        elif isinstance(b, dict) and b.get("url") and b.get("format", "normal") in ("normal", "gallery"):
            bilder.append(b["url"])
    bilder.sort(key=lambda u: 0 if "/images/" in u else 1)
    tumnagel = _hamta(post, "thumbnailLink")
    if not bilder and tumnagel:
        bilder = [tumnagel]

    skick = ""
    for attr in ((_hamta(post, "attributeValues", default={}) or {}).get("termAttributeValues") or []):
        if attr.get("name") == "condition" and attr.get("values"):
            skick = ", ".join(attr["values"])

    slutar, slutar_ts = "", None
    slut = _hamta(post, "endDate")
    if slut:
        try:
            dt = datetime.fromisoformat(slut.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            slutar = dt.astimezone().strftime("%-d/%-m %H:%M")
            slutar_ts = int(dt.timestamp())
        except ValueError:
            pass

    url = _hamta(post, "itemUrl", "itemLink") or f"https://www.tradera.com/item/{item_id}"
    if url.startswith("/"):
        url = "https://www.tradera.com" + url
    url = url.replace("http://", "https://", 1)
    if _hamta(post, "isEnded", default=False):
        return None

    return Annons(
        kalla="tradera",
        id=str(item_id),
        titel=(_hamta(post, "shortDescription", "title", default="") or "").strip(),
        url=url,
        beskrivning=((_hamta(post, "longDescription", default="") or "")[:1500] + (f"\nSkick: {skick}" if skick else "")).strip(),
        plats="Tradera",
        pris=pris,
        pris_text=pris_text,
        bilder=list(dict.fromkeys(bilder)),
        slutar=slutar,
        slutar_ts=slutar_ts,
        kategori=kategori,
    )


def _poster(data) -> list[dict]:
    if isinstance(data, list):
        return data
    for nyckel in ("items", "Items", "item", "Item"):
        if isinstance(data.get(nyckel), list):
            return data[nyckel]
    return []


def sok(fraga: str, kategori: str = "", sidor: int = 1) -> list[Annons]:
    headers = {
        "X-App-Id": os.environ["TRADERA_APP_ID"],
        "X-App-Key": os.environ["TRADERA_APP_KEY"],
        "Accept": "application/json",
    }
    resultat = []
    for sida in range(1, sidor + 1):
        r = requests.get(
            API,
            params={"query": fraga, "pageNumber": sida, "orderBy": "Relevance"},
            headers=headers,
            timeout=30,
        )
        if r.status_code == 429:
            print("  Tradera: dagskvoten är slut, hoppar över resten.")
            break
        r.raise_for_status()
        for post in _poster(r.json()):
            a = tolka(post, kategori)
            if a:
                resultat.append(a)
        time.sleep(1)
    return resultat
