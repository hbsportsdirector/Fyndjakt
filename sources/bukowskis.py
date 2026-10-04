"""Bukowskis – läser sökresultatsidan (server-renderad HTML). Ingen nyckel behövs.
Sök-URL: /sv/lots/search/<ord>, nästa sida: /sv/lots/page/<n>/search/<ord> (ca 100 per sida)."""
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from . import Annons

BAS = "https://www.bukowskis.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Fyndjakt; privat bevakning)", "Accept-Language": "sv-SE,sv;q=0.9"}
KURSER = {"SEK": 1, "EUR": 11.2}


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _belopp(text: str) -> tuple[int | None, str]:
    """'12 000 SEK' -> (12000, 'SEK')"""
    m = re.search(r"([\d\s ]+)\s*([A-Z]{3})", text or "")
    if not m:
        return None, ""
    siffror = re.sub(r"\D", "", m.group(1))
    return (int(siffror) if siffror else None), m.group(2)


def tolka_kort(kort, kategori: str = "") -> Annons | None:
    lank = kort.select_one("a.c-lot-index-lot__title-link") or kort.select_one("a[href*='/lots/']")
    if not lank:
        return None
    url = urljoin(BAS, lank["href"])
    m = re.search(r"/lots/(\d+)", url)
    if not m:
        return None

    artist = _text(kort.select_one(".c-lot-index-lot__artist"))
    titel = _text(kort.select_one(".c-lot-index-lot__title"))
    full_titel = f"{artist} {titel}".strip() or _text(lank)

    bud_text = _text(kort.select_one(".c-lot-index-lot__result-value"))
    utrop_text = _text(kort.select_one(".c-lot-index-lot__estimate-value"))
    bud, valuta_b = _belopp(bud_text)
    utrop, valuta_u = _belopp(utrop_text)
    valuta = valuta_b or valuta_u or "SEK"
    belopp = bud or utrop
    pris = round(belopp * KURSER[valuta]) if belopp and valuta in KURSER else None
    pris_text = f"Bud {bud_text}" if bud else (f"Utrop {utrop_text}" if utrop_text else bud_text)
    if valuta != "SEK" and pris:
        pris_text += f" (≈ {pris:,} kr)".replace(",", " ")

    slutar_ts, slutar = None, ""
    nedrakning = kort.select_one("[data-end-date]")
    if nedrakning and nedrakning["data-end-date"].isdigit():
        slutar_ts = int(nedrakning["data-end-date"])
        slutar = datetime.fromtimestamp(slutar_ts, timezone.utc).astimezone().strftime("%-d/%-m %H:%M")
        if slutar_ts < time.time():
            return None

    bild = kort.select_one("img.o-aspect-ratio__image") or kort.select_one("img")
    bilder = []
    if bild:
        tum = bild.get("data-thumbnails")
        if tum:
            bilder = re.findall(r"https://[^\"',\]]+", tum.replace("&quot;", '"'))
        if not bilder and bild.get("src", "").startswith("http"):
            bilder = [bild["src"]]

    return Annons(
        kalla="bukowskis",
        id=m.group(1),
        titel=full_titel,
        url=url,
        pris=pris,
        pris_text=pris_text,
        bilder=bilder[:4],
        plats="Bukowskis",
        slutar=slutar,
        slutar_ts=slutar_ts,
        kategori=kategori,
        valuta=valuta,
    )


def tolka_sida(html: str, kategori: str = "") -> list[Annons]:
    soup = BeautifulSoup(html, "lxml")
    return [a for a in (tolka_kort(k, kategori) for k in soup.select("div.c-lot-index-lot")) if a]


def sok(fraga: str, kategori: str = "", sidor: int = 3) -> list[Annons]:
    resultat = []
    for sida in range(1, sidor + 1):
        sokvag = f"/sv/lots/search/{quote(fraga)}" if sida == 1 else f"/sv/lots/page/{sida}/search/{quote(fraga)}"
        r = requests.get(BAS + sokvag, headers=HEADERS, timeout=30)
        r.raise_for_status()
        traffar = tolka_sida(r.text, kategori)
        resultat += traffar
        if len(traffar) < 90:  # sista sidan
            break
        time.sleep(1.5)
    return resultat


def tolka_lotsida(html: str) -> tuple[str, str]:
    """Returnerar (ort, beskrivning) från en lot-sida.
    Placering ser ut som 'Västberga Allé 3, Hägersten - H138'."""
    soup = BeautifulSoup(html, "lxml")
    placering = _text(soup.select_one(".c-lot-placement__value"))
    ort = placering.split(" - ")[0].split(",")[-1].strip() if placering else ""
    beskrivning = _text(soup.select_one(".c-lot-description"))
    return ort, beskrivning


def berika(a: Annons) -> None:
    """Hämtar lot-sidan för ort och beskrivning (görs bara för annonser som ska bedömas)."""
    r = requests.get(a.url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    ort, beskrivning = tolka_lotsida(r.text)
    if ort:
        a.plats = f"Bukowskis, {ort}"
    if beskrivning:
        a.beskrivning = beskrivning[:1500]
    time.sleep(1)
