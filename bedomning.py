"""Låter Claude titta på bilderna och texten och betygsätta hur väl annonsen passar din stil."""
import json
import os
import re

import anthropic

from sources import Annons

INSTRUKTION = """Du är en erfaren inredare som letar begagnade fynd åt en kund.
Här är kundens stilprofil:

<stilprofil>
{stil}
</stilprofil>

Bedöm annonsen nedan: hur väl passar föremålet in i kundens hem?
Titta främst på bilderna (material, färg, form, patina, kvalitet), och använd texten för detaljer.
Var kräsen: 9–10 = exakt rätt och ett fynd, 7–8 = passar bra, 4–6 = kanske, 0–3 = fel stil.
Räkna ner om föremålet ser massproducerat, trasigt eller felaktigt ut på bilderna.

Svara ENBART med JSON, utan annan text:
{{"betyg": <heltal 0-10>, "motivering": "<en mening på svenska om varför>"}}"""


def _klient() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def bedom(annons: Annons, stilprofil: str, modell: str, klient=None) -> tuple[int, str]:
    klient = klient or _klient()
    text = (
        f"Titel: {annons.titel}\n"
        f"Pris: {annons.pris_text}\n"
        f"Plats: {annons.plats}\n"
        f"Beskrivning: {annons.beskrivning[:1200]}"
    )
    innehall = [{"type": "image", "source": {"type": "url", "url": u}} for u in annons.bilder[:3]]
    innehall.append({"type": "text", "text": text})

    def fraga(med_bilder: bool):
        delar = innehall if med_bilder else [innehall[-1]]
        return klient.messages.create(
            model=modell,
            max_tokens=200,
            system=INSTRUKTION.format(stil=stilprofil),
            messages=[{"role": "user", "content": delar}],
        )

    try:
        svar = fraga(med_bilder=True)
    except anthropic.BadRequestError:
        # T.ex. en bild som inte gick att hämta – försök med bara text.
        svar = fraga(med_bilder=False)

    return tolka_svar(svar.content[0].text)


def tolka_svar(text: str) -> tuple[int, str]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return 0, "Kunde inte tolka svaret"
    try:
        data = json.loads(match.group(0))
        return int(data.get("betyg", 0)), str(data.get("motivering", "")).strip()
    except (ValueError, json.JSONDecodeError):
        return 0, "Kunde inte tolka svaret"
