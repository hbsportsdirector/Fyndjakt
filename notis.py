"""Skickar träffar till Telegram."""
import html
import os

import requests

from sources import Annons


def aktiverad() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def _api(metod: str) -> str:
    return f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{metod}"


def formatera(a: Annons, betyg: int, motivering: str) -> str:
    stjarnor = "★" * round(betyg / 2) + "☆" * (5 - round(betyg / 2))
    rader = [
        f"<b>{html.escape(a.titel[:200])}</b>",
        f"{stjarnor}  {betyg}/10 · {html.escape(a.kategori)}",
        f"<i>{html.escape(motivering)}</i>",
        "",
        f"💰 {html.escape(a.pris_text)}",
    ]
    if a.plats:
        rader.append(f"📍 {html.escape(a.plats)}")
    if a.slutar:
        rader.append(f"⏳ Slutar {a.slutar}")
    rader.append(f'🔗 <a href="{html.escape(a.url)}">Öppna på {a.kalla.capitalize()}</a>')
    sajt = os.getenv("SAJT_URL")
    if sajt:
        rader.append(f'📚 <a href="{html.escape(sajt)}">Alla fynd</a>')
    return "\n".join(rader)


def skicka(a: Annons, betyg: int, motivering: str) -> None:
    chat = os.environ["TELEGRAM_CHAT_ID"]
    text = formatera(a, betyg, motivering)
    if a.bilder and len(text) <= 1024:
        r = requests.post(
            _api("sendPhoto"),
            data={"chat_id": chat, "photo": a.bilder[0], "caption": text, "parse_mode": "HTML"},
            timeout=30,
        )
        if r.ok:
            return
    r = requests.post(
        _api("sendMessage"),
        data={"chat_id": chat, "text": text, "parse_mode": "HTML"},
        timeout=30,
    )
    r.raise_for_status()


def skicka_text(text: str) -> None:
    requests.post(
        _api("sendMessage"),
        data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text, "parse_mode": "HTML"},
        timeout=30,
    ).raise_for_status()
