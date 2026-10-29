"""Miniatyrbilder per fynd i databasen (fyndjakt_bilder), så att andra appar kan visa en bild per fynd.

Bilder från Tradera/Auctionet går inte att visa direkt från andra sidor – därför sparas en liten
JPEG (max 200 px) som data-URL. Bilden som redan hämtats för Claudes bedömning återanvänds.
"""
import base64
import io
import time

import requests

import bedomning
import smak

MINI_MAX = 200      # pixlar på längsta sidan
MINI_KVALITET = 70  # JPEG-kvalitet – typiskt 5–10 kB
SATS = 100          # miniatyrer per anrop när de sparas


def mini(data: bytes) -> tuple[str, int, int]:
    """Bildens bytes → (data-URL med JPEG, bredd, höjd), max MINI_MAX px på längsta sidan."""
    from PIL import Image
    bild = Image.open(io.BytesIO(data)).convert("RGB")
    bild.thumbnail((MINI_MAX, MINI_MAX))
    ut = io.BytesIO()
    bild.save(ut, "JPEG", quality=MINI_KVALITET, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(ut.getvalue()).decode(), bild.width, bild.height


def _hamta(url: str) -> bytes:
    r = requests.get(url, timeout=20, headers={"User-Agent": "Fyndjakt/1.0 (privat bevakning)"})
    r.raise_for_status()
    return r.content


def bytes_for(url: str, hamta: bool = True) -> bytes | None:
    """Bilden som redan hämtats för bedömningen om den finns, annars hämtas den (om hamta)."""
    if url in bedomning._BILDER:
        b64 = bedomning._BILDER[url]
        return base64.b64decode(b64) if b64 else None  # None = gick inte att hämta i natt – försök inte igen
    return _hamta(url) if hamta else None


def _rpc(ans: tuple[str, str, str], namn: str, **varden):
    url, nyckel, token = ans
    r = requests.post(f"{url}/rest/v1/rpc/{namn}", json={"token": token, **varden},
                      headers={"apikey": nyckel, "Content-Type": "application/json"}, timeout=60)
    r.raise_for_status()
    return r.json()


def synka(cfg: dict, paus: float = 0.0) -> dict:
    """Skapar miniatyrer för alla fynd i användarnas data.poster som saknar en. Bilder som inte går
    att hämta eller läsa hoppas över tyst. paus = sekunder mellan hämtningar från nätet."""
    ans = smak._anslutning(cfg)
    if not ans:
        return {}
    saknas = _rpc(ans, "fyndjakt_bilder_saknas")
    klara, misslyckade, hamtade, sparade = [], 0, 0, 0
    for rad in saknas:
        url = rad.get("bild") or ""
        if url not in bedomning._BILDER:
            hamtade += 1
            if paus and hamtade > 1:
                time.sleep(paus)
        try:
            data = bytes_for(url)
            if not data:
                misslyckade += 1
                continue
            data_url, bredd, hojd = mini(data)
            klara.append({"nyckel": rad["nyckel"], "mini": data_url, "bredd": bredd, "hojd": hojd})
        except Exception:
            misslyckade += 1
            continue
        if len(klara) >= SATS:
            sparade += _rpc(ans, "fyndjakt_bilder_spara", bilder=klara)
            klara = []
    if klara:
        sparade += _rpc(ans, "fyndjakt_bilder_spara", bilder=klara)
    print(f"Miniatyrer: {sparade} nya ({hamtade} hämtade, {misslyckade} misslyckade) av {len(saknas)} som saknades.")
    return {"saknades": len(saknas), "nya": sparade, "hamtade": hamtade, "misslyckade": misslyckade}


def stada(cfg: dict) -> int:
    """Tar bort miniatyrer för fynd som inte längre finns i någon användares data.poster."""
    ans = smak._anslutning(cfg)
    if not ans:
        return 0
    n = _rpc(ans, "fyndjakt_bilder_stada")
    print(f"Miniatyrer: {n} gamla borttagna.")
    return n
