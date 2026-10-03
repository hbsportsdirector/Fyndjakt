"""Auctionet – Skandinaviens största auktionsplattform (500+ auktionshus).
Använder Auctionets öppna JSON-API. Ingen nyckel behövs."""
import html
import re
import time
from datetime import datetime, timezone

import requests

from . import Annons

API = "https://auctionet.com/api/v2/items.json"
HEADERS = {"User-Agent": "Fyndjakt/1.0 (privat bevakning)"}


def _rensa_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def tolka(post: dict, kategori: str = "") -> Annons | None:
    if post.get("state") != "published":
        return None
    slutar_ts = post.get("ends_at")
    if slutar_ts and slutar_ts < time.time():
        return None

    bud = post.get("bids") or []
    hogsta = max((b.get("amount", 0) for b in bud), default=0)
    utrop = post.get("estimate") or 0
    valuta = post.get("currency", "SEK")
    pris = hogsta or utrop or None
    pris_text = f"Bud {hogsta} {valuta}" if hogsta else f"Utrop {utrop} {valuta}"

    bilder = [b.get("w640") or b.get("hd") for b in post.get("images") or []]
    beskrivning = _rensa_html(post.get("description"))
    skick = _rensa_html(post.get("condition"))
    if skick:
        beskrivning += f"\nSkick: {skick}"

    slutar = ""
    if slutar_ts:
        slutar = datetime.fromtimestamp(slutar_ts, timezone.utc).astimezone().strftime("%-d/%-m %H:%M")

    plats = ", ".join(p for p in [post.get("house"), post.get("location")] if p)
    url = (post.get("url") or "").replace("auctionet.com/en/", "auctionet.com/sv/")

    return Annons(
        kalla="auctionet",
        id=str(post["id"]),
        titel=post.get("title", "").strip(),
        url=url,
        beskrivning=beskrivning,
        pris=pris,
        pris_text=pris_text,
        bilder=[b for b in bilder if b],
        plats=plats,
        slutar=slutar,
        slutar_ts=slutar_ts,
        kategori=kategori,
    )


def sok(fraga: str, kategori: str = "", sidor: int = 2, per_sida: int = 48) -> list[Annons]:
    resultat = []
    for sida in range(1, sidor + 1):
        r = requests.get(
            API,
            params={"q": fraga, "per_page": per_sida, "page": sida},
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        for post in data.get("items", []):
            a = tolka(post, kategori)
            if a:
                resultat.append(a)
        if sida >= (data.get("pagination") or {}).get("total_pages", 1):
            break
        time.sleep(1)  # var snäll mot servern
    return resultat
