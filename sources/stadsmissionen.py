"""Stockholms Stadsmission – webbutiken på stadsmissionen.se/shop.
Butiken har ingen sökning som går att länka till, så hela kategorin (t.ex. "hem") läses
en gång per körning (16 produkter per sida, ?page=0,1,2 …) och sökorden matchas lokalt."""
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from . import Annons

BAS = "https://www.stadsmissionen.se"
HEADERS = {"User-Agent": "Mozilla/5.0 (Fyndjakt; privat bevakning)", "Accept-Language": "sv-SE,sv;q=0.9"}
KATEGORIER = ["hem"]
MAX_SIDOR = 120

_katalog: list[Annons] | None = None


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def tolka_rad(rad) -> Annons | None:
    lank = rad.select_one(".title a") or rad.select_one("a[href*='/shop/produkt/']")
    if not lank:
        return None
    url = urljoin(BAS, lank["href"])
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    marke = _text(rad.select_one(".pre-heading"))
    titel = _text(lank)
    if marke and marke.lower() != "okänt märke" and marke.lower() not in titel.lower():
        titel = f"{marke} – {titel}"
    pris_text = _text(rad.select_one(".price")).replace("kr kr", "kr")
    siffror = re.sub(r"\D", "", pris_text)
    bilder = [urljoin(BAS, i["src"]) for i in rad.select("img[src]")][:4]
    return Annons(
        kalla="stadsmissionen",
        id=slug,
        titel=titel,
        url=url,
        beskrivning=_text(rad.select_one(".tags")),
        pris=int(siffror) if siffror else None,
        pris_text=f"Köp nu {pris_text}" if pris_text else "",
        bilder=bilder,
        plats="Stockholms Stadsmission",
    )


def tolka_sida(html: str) -> list[Annons]:
    soup = BeautifulSoup(html, "lxml")
    return [a for a in (tolka_rad(r) for r in soup.select(".views-row")) if a]


def katalog() -> list[Annons]:
    """Hämtar hela kategorin en gång per körning."""
    global _katalog
    if _katalog is not None:
        return _katalog
    alla: dict[str, Annons] = {}
    _katalog = []  # så att ett fel inte gör om hämtningen för varje sökord
    for kat in KATEGORIER:
        for sida in range(MAX_SIDOR):
            r = requests.get(f"{BAS}/shop/{kat}", params={"page": sida}, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                break
            r.raise_for_status()
            nya = [a for a in tolka_sida(r.text) if a.id not in alla]
            if not nya:
                break
            for a in nya:
                alla[a.id] = a
            time.sleep(1)
    _katalog = list(alla.values())
    print(f"  Stadsmissionen: {len(_katalog)} produkter i katalogen")
    return _katalog


def matchar(fraga: str, a: Annons) -> bool:
    """Alla ord i sökningen måste finnas i titeln. För sökningar som "bokhylla valnöt"
    räcker huvudordet ("bokhylla") – katalogen är liten och AI:n sköter urvalet.
    Namn (t.ex. "Erik Höglund") måste matcha helt."""
    text = f"{a.titel} {a.beskrivning}".lower()
    ord_ = fraga.split()
    if all(o.lower() in text for o in ord_):
        return True
    forsta = ord_[0]
    return len(ord_) > 1 and forsta.islower() and len(forsta) >= 5 and forsta in text


def sok(fraga: str, kategori: str = "") -> list[Annons]:
    ut = []
    for a in katalog():
        if matchar(fraga, a):
            kopia = Annons(**{**a.__dict__, "bilder": list(a.bilder), "kategori": kategori})
            ut.append(kopia)
    return ut
