"""Låter Claude titta på bilderna och texten och betygsätta hur väl annonsen passar din stil."""
import json
import os
import re

import anthropic

from sources import Annons

STANDARD_KALIBRERING = """Var MYCKET kräsen – kunden vill bara se ett fåtal utvalda fynd, inte allt som "passar".
Ungefär 1 av 10 annonser bör få 8 eller mer, och 9–10 är sällsynt.
- 10: Ett unikt fynd med karaktär och historia som skulle bli ett blickfång i rummet.
- 9: Exakt rätt stil, material och kvalitet, och något utöver det vanliga.
- 8: Mycket bra match, väl värt att titta på.
- 6–7: Passar stilen men är vardagligt, vanligt förekommande eller utan särskild karaktär.
- 4–5: Kanske, men något skaver (fel färg, epok, kvalitet eller storlek).
- 0–3: Fel stil, eller sådant kunden redan har.
Räkna ner för massproducerat, nytillverkat i gammal stil, trasigt, dåliga bilder,
och för helt vanliga föremål som det finns tusentals likadana av."""

INSTRUKTION = """Du är en erfaren inredare och samlingsrådgivare som letar begagnade fynd åt en kund.
Här är kundens profil:

<stilprofil>
{stil}
</stilprofil>

Bedöm annonsen nedan: hur väl passar föremålet kundens profil?
Titta främst på bilderna (material, färg, form, patina, kvalitet), och använd texten för detaljer.

{kalibrering}

Ge också en kort sökfras (2–4 ord, på svenska) som hittar JÄMFÖRBARA föremål på en
auktionssajt, för prisjämförelse. Använd konstnär/formgivare/tillverkare + föremålstyp om det
finns, annars föremålstyp + material/epok. Exempel: "Erik Höglund vas", "bokskåp mahogny",
"jordglob 1930-tal", "Stig Lindberg fat".

Svara ENBART med JSON, utan annan text:
{{"betyg": <heltal 0-10>, "motivering": "<EN kort mening på svenska, max 30 ord>", "jamforsok": "<sökfras>"}}"""


def _klient() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def bedom(annons: Annons, stilprofil: str, modell: str, klient=None,
          kalibrering: str | None = None) -> tuple[int, str, str]:
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
            max_tokens=400,
            system=INSTRUKTION.format(stil=stilprofil, kalibrering=(kalibrering or STANDARD_KALIBRERING).strip()),
            messages=[{"role": "user", "content": delar}],
        )

    med_bilder = True
    for forsok in range(2):
        try:
            svar = fraga(med_bilder)
        except anthropic.BadRequestError:
            # T.ex. en bild som inte gick att hämta – försök med bara text.
            med_bilder = False
            svar = fraga(med_bilder)
        text = "".join(b.text for b in svar.content if getattr(b, "type", "text") == "text")
        resultat = tolka_svar(text)
        if resultat[1] != "Kunde inte tolka svaret":
            return resultat
    return resultat


def tolka_svar(text: str) -> tuple[int, str, str]:
    """Returnerar (betyg, motivering, jämförelsesökning)."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return _raddning(text)
    try:
        data = json.loads(match.group(0))
        return (int(data.get("betyg", 0)), str(data.get("motivering", "")).strip(),
                str(data.get("jamforsok", "") or "").strip())
    except (ValueError, json.JSONDecodeError):
        return _raddning(text)


def _raddning(text: str) -> tuple[int, str, str]:
    """Plockar ut betyg och motivering ur ett avklippt eller trasigt svar."""
    b = re.search(r'"betyg"\s*:\s*"?(\d+)', text)
    if not b:
        return 0, "Kunde inte tolka svaret", ""
    m = re.search(r'"motivering"\s*:\s*"([^"]*)', text)
    j = re.search(r'"jamforsok"\s*:\s*"([^"]*)"', text)
    return int(b.group(1)), (m.group(1).strip() if m else ""), (j.group(1).strip() if j else "")


def foresla_jamforsok(titel: str, modell: str, klient=None) -> str:
    """Billig textfråga för äldre fynd som saknar jämförelsesökning."""
    klient = klient or _klient()
    svar = klient.messages.create(
        model=modell,
        max_tokens=40,
        messages=[{"role": "user", "content":
                   "Ge en kort sökfras (2–4 ord, svenska) som hittar jämförbara föremål på en "
                   "auktionssajt för prisjämförelse – konstnär/tillverkare + föremålstyp om det finns, "
                   "annars föremålstyp + material/epok. Svara bara med frasen.\n\nTitel: " + titel}],
    )
    return svar.content[0].text.strip().strip('"').splitlines()[0][:60]
