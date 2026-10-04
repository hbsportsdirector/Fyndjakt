"""Låter Claude titta på bilderna och texten och betygsätta hur väl annonsen passar din stil."""
import json
import os
import re

import anthropic

from sources import Annons

INSTRUKTION = """Du är en erfaren inredare och samlingsrådgivare som letar begagnade fynd åt en kund.
Här är kundens profil:

<stilprofil>
{stil}
</stilprofil>

Bedöm annonsen nedan: hur väl passar föremålet kundens profil?
Titta främst på bilderna (material, färg, form, patina, kvalitet), och använd texten för detaljer.

Var MYCKET kräsen – kunden vill bara se ett fåtal utvalda fynd, inte allt som "passar".
Ungefär 1 av 10 annonser bör få 8 eller mer, och 9–10 är sällsynt.
- 10: Ett unikt fynd med karaktär och historia som skulle bli ett blickfång i rummet.
- 9: Exakt rätt stil, material och kvalitet, och något utöver det vanliga.
- 8: Mycket bra match, väl värt att titta på.
- 6–7: Passar stilen men är vardagligt, vanligt förekommande eller utan särskild karaktär.
- 4–5: Kanske, men något skaver (fel färg, epok, kvalitet eller storlek).
- 0–3: Fel stil, eller sådant kunden redan har.
Räkna ner för massproducerat, nytillverkat i gammal stil, trasigt, dåliga bilder,
och för helt vanliga föremål som det finns tusentals likadana av.

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
