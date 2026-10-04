"""Myrorna – läser sökresultaten på myrorna.se/shop (auktionerna avgörs på Tradera).
Sök: /shop/?s=<ord>, nästa sida: /shop/sida/<n>/?s=<ord> (50 per sida). Ingen nyckel behövs."""
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from . import Annons

BAS = "https://www.myrorna.se"
HEADERS = {"User-Agent": "Mozilla/5.0 (Fyndjakt; privat bevakning)", "Accept-Language": "sv-SE,sv;q=0.9"}


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def tolka_kort(kort, kategori: str = "") -> Annons | None:
    lank = kort.select_one("a[href*='/shop/annons/']")
    if not lank:
        return None
    url = lank["href"]
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    titel = _text(kort.select_one("h2")) or (kort.select_one("img") or {}).get("alt", "")

    bud_el = kort.select_one(".auctions-listing__item__details__max-bid")
    bud_text = _text(bud_el)
    etikett = _text(bud_el.select_one(".auctions-listing__item__details__label")) if bud_el else ""
    belopp_text = bud_text.replace(etikett, "").strip()
    siffror = re.sub(r"\D", "", belopp_text)
    pris = int(siffror) if siffror else None
    pris_text = f"{etikett or 'Pris'} {belopp_text}".strip() if belopp_text else ""

    slutar_ts, slutar = None, ""
    nedrakning = kort.select_one("[data-end-date]")
    if nedrakning:
        try:
            dt = datetime.fromisoformat(nedrakning["data-end-date"])
            slutar_ts = int(dt.timestamp())
            slutar = dt.astimezone().strftime("%-d/%-m %H:%M")
            if slutar_ts < time.time():
                return None
        except ValueError:
            pass

    bild = kort.select_one("img")
    bilder = [bild["src"]] if bild and bild.get("src", "").startswith("http") else []

    return Annons(
        kalla="myrorna",
        id=kort.get("data-post-id") or slug,
        titel=titel,
        url=url,
        pris=pris,
        pris_text=pris_text,
        bilder=bilder,
        plats="Myrorna, Ropsten",  # webbshoppen säljs från butiken i Ropsten, Stockholm
        slutar=slutar,
        slutar_ts=slutar_ts,
        kategori=kategori,
    )


def tolka_sida(html: str, kategori: str = "") -> list[Annons]:
    soup = BeautifulSoup(html, "lxml")
    return [a for a in (tolka_kort(k, kategori) for k in soup.select("div.auctions-listing__item")) if a]


def sok(fraga: str, kategori: str = "", sidor: int = 3) -> list[Annons]:
    resultat = []
    for sida in range(1, sidor + 1):
        url = f"{BAS}/shop/" if sida == 1 else f"{BAS}/shop/sida/{sida}/"
        r = requests.get(url, params={"s": fraga}, headers=HEADERS, timeout=30)
        if r.status_code == 404:
            break
        r.raise_for_status()
        traffar = tolka_sida(r.text, kategori)
        resultat += traffar
        if len(traffar) < 45:
            break
        time.sleep(1.5)
    return resultat
