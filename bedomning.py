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


BILDER = 1          # bild per annons – huvudbilden räcker för stil, färg och form
GRUPPSTORLEK = 5    # annonser per anrop i batchen – profilen skickas en gång per grupp i stället för per annons

GRUPP_INSTRUKTION = """Du är en erfaren inredare och samlingsrådgivare som letar begagnade fynd åt en kund.
Här är kundens profil:

<stilprofil>
{stil}
</stilprofil>

Du får flera annonser, numrerade "Annons 1", "Annons 2" … – varje annons med sin text och sina bilder direkt efter.
Bedöm VARJE annons för sig: hur väl passar föremålet kundens profil?
Titta främst på bilderna (material, färg, form, patina, kvalitet), och använd texten för detaljer.
Blanda inte ihop annonserna – bilderna hör till annonsen som står närmast före dem.

{kalibrering}

Ge också för varje annons en kort sökfras (2–4 ord, på svenska) som hittar JÄMFÖRBARA föremål på en
auktionssajt, för prisjämförelse: konstnär/formgivare/tillverkare + föremålstyp om det finns, annars
föremålstyp + material/epok.

Svara ENBART med en JSON-lista, en post per annons, utan annan text:
[{{"nr": 1, "betyg": <heltal 0-10>, "motivering": "<EN kort mening på svenska, max 30 ord>", "jamforsok": "<sökfras>"}}, …]"""


def grupp_forfragan(annonser: list, stilprofil: str, modell: str, kalibrering: str | None = None) -> dict:
    """Flera annonser i ett anrop (samma spår/profil)."""
    innehall = []
    for nr, a in enumerate(annonser, 1):
        innehall.append({"type": "text", "text": (
            f"Annons {nr}:\nTitel: {a.titel}\nPris: {a.pris_text}\nPlats: {a.plats}\n"
            f"Beskrivning: {a.beskrivning[:700]}")})
        innehall += [{"type": "image", "source": {"type": "url", "url": u}} for u in a.bilder[:BILDER]]
    return {
        "model": modell,
        "max_tokens": 150 * len(annonser) + 50,
        "system": GRUPP_INSTRUKTION.format(stil=stilprofil, kalibrering=(kalibrering or STANDARD_KALIBRERING).strip()),
        "messages": [{"role": "user", "content": innehall}],
    }


def tolka_grupp(text: str, antal: int) -> dict[int, tuple[int, str, str]]:
    """{nr: (betyg, motivering, jämförelsesökning)} – det som saknas eller är trasigt bedöms sedan en och en."""
    ut = {}
    match = re.search(r"\[.*\]", text, re.S)
    poster = []
    if match:
        try:
            poster = json.loads(match.group(0))
        except (ValueError, json.JSONDecodeError):
            poster = []
    if not poster:  # avklippt svar – rädda de poster som är hela
        for m in re.finditer(r"\{[^{}]*\}", text):
            try:
                poster.append(json.loads(m.group(0)))
            except (ValueError, json.JSONDecodeError):
                pass
    for d in poster:
        try:
            nr = int(d.get("nr"))
            if 1 <= nr <= antal and "betyg" in d:
                ut[nr] = (max(0, min(10, int(d["betyg"]))), str(d.get("motivering", "")).strip(),
                          str(d.get("jamforsok", "") or "").strip())
        except (TypeError, ValueError, AttributeError):
            continue
    return ut


def _klient() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def forfragan(annons: Annons, stilprofil: str, modell: str, kalibrering: str | None = None,
              med_bilder: bool = True) -> dict:
    """Parametrarna till ett bedömningsanrop – samma för vanliga anrop och batch."""
    text = (
        f"Titel: {annons.titel}\n"
        f"Pris: {annons.pris_text}\n"
        f"Plats: {annons.plats}\n"
        f"Beskrivning: {annons.beskrivning[:1200]}"
    )
    innehall = [{"type": "image", "source": {"type": "url", "url": u}} for u in annons.bilder[:BILDER]] if med_bilder else []
    innehall.append({"type": "text", "text": text})
    return {
        "model": modell,
        "max_tokens": 400,
        "system": INSTRUKTION.format(stil=stilprofil, kalibrering=(kalibrering or STANDARD_KALIBRERING).strip()),
        "messages": [{"role": "user", "content": innehall}],
    }


def _text(svar) -> str:
    return "".join(b.text for b in svar.content if getattr(b, "type", "text") == "text")


def bedom(annons: Annons, stilprofil: str, modell: str, klient=None,
          kalibrering: str | None = None) -> tuple[int, str, str]:
    klient = klient or _klient()
    med_bilder = True
    for forsok in range(2):
        try:
            svar = klient.messages.create(**forfragan(annons, stilprofil, modell, kalibrering, med_bilder))
        except anthropic.BadRequestError:
            # T.ex. en bild som inte gick att hämta – försök med bara text.
            med_bilder = False
            svar = klient.messages.create(**forfragan(annons, stilprofil, modell, kalibrering, med_bilder))
        resultat = tolka_svar(_text(svar))
        if resultat[1] != "Kunde inte tolka svaret":
            return resultat
    return resultat


def _avsluta_batch(klient, batch_id: str, intervall: int):
    """Avbryter en batch som dröjer och väntar (högst ~10 min) tills den är avslutad,
    så att det som hann bli klart kan hämtas."""
    import time
    klient.messages.batches.cancel(batch_id)
    for _ in range(max(1, 600 // max(intervall, 1))):
        if klient.messages.batches.retrieve(batch_id).processing_status == "ended":
            return True
        time.sleep(intervall)
    return False


def bedom_batch(forfragningar: dict[str, dict], klient=None, max_vant: int = 40 * 60,
                intervall: int = 30) -> dict[str, tuple[int, str, str]]:
    """Skickar alla bedömningar som EN batch (halva priset) och väntar på svaren.
    Returnerar {id: (betyg, motivering, jämförelsesökning)} för de som lyckades och gick att tolka;
    resten (fel, avbrutna, otolkbara) saknas i svaret och bedöms sedan med vanliga anrop."""
    import time
    if not forfragningar:
        return {}
    klient = klient or _klient()
    batch = klient.messages.batches.create(
        requests=[{"custom_id": cid, "params": params} for cid, params in forfragningar.items()])
    print(f"  Batch {batch.id} skickad med {len(forfragningar)} bedömningar – väntar på svar …")
    start = time.time()
    while True:
        batch = klient.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        if time.time() - start > max_vant:
            print("  Batchen tog för lång tid – sparar det som hann bli klart och bedömer resten direkt.")
            if not _avsluta_batch(klient, batch.id, intervall):
                return {}
            break
        time.sleep(intervall)
    ut = {}
    for rad in klient.messages.batches.results(batch.id):
        if rad.result.type != "succeeded":
            continue
        tolkat = tolka_svar(_text(rad.result.message))
        if tolkat[1] != "Kunde inte tolka svaret":
            ut[rad.custom_id] = tolkat
    print(f"  Batch klar efter {round((time.time() - start) / 60)} min: {len(ut)} av {len(forfragningar)} bedömda.")
    return ut


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


# ── Snabbsållning: titel + pris för många annonser i taget ───────────────────
SALL_INSTRUKTION = """Du sållar annonser åt en kund som letar begagnade fynd. Här är kundens profil:

<stilprofil>
{stil}
</stilprofil>

Du får en numrerad lista med annonser (bara titel och pris). Ge varje annons ett SNABBT betyg 0–10 för hur
troligt det är att den passar profilen, utifrån enbart titeln. Var generös med det som KAN passa (6 eller mer) –
bilderna granskas sedan noggrant. Ge lågt betyg (0–4) åt det som uppenbart är fel: fel sorts föremål,
reservdelar, kläder, böcker OM ämnet, affischer och tryck, nytillverkat, samt sådant kunden redan har.

Föremål av en namngiven formgivare, konstnär, fabrik eller serie som nämns i profilen eller reglerna nedan ska
ALLTID få minst 6 – även om titeln är kort eller osäker ("troligen", "möjligen") – så att bilderna får avgöra.
{regler}
Svara ENBART med JSON där nyckeln är numret och värdet betyget, t.ex. {{"1": 7, "2": 2}}."""


def sall_forfragan(annonser: list, stilprofil: str, modell: str, regler: str | None = None) -> dict:
    lista = "\n".join(f"{i}. {a.titel[:140]} | {a.pris_text}" for i, a in enumerate(annonser, 1))
    return {"model": modell, "max_tokens": 20 + 9 * len(annonser),
            "system": SALL_INSTRUKTION.format(stil=stilprofil, regler=(
                f"\nKundens bedömningsregler:\n{regler.strip()}\n" if regler else "")),
            "messages": [{"role": "user", "content": lista}]}


def tolka_sallning(text: str, antal: int) -> dict[int, int]:
    match = re.search(r"\{.*\}", text, re.S)
    ut = {}
    if match:
        try:
            for k, v in json.loads(match.group(0)).items():
                if str(k).isdigit() and 1 <= int(k) <= antal:
                    ut[int(k)] = max(0, min(10, int(v)))
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    if not ut:  # avklippt svar – plocka det som går
        for k, v in re.findall(r'"(\d+)"\s*:\s*(\d+)', text):
            if 1 <= int(k) <= antal:
                ut[int(k)] = min(10, int(v))
    return ut


def salla(grupper: dict[str, tuple], modell: str, klient=None, storlek: int = 80) -> dict[str, int]:
    """grupper: {spår: (profil, [annonser]) eller (profil, [annonser], regler)}. Returnerar {annonsnyckel: snabbetyg}.
    Allt skickas i en batch (halva priset); annonser utan svar saknas i resultatet och går vidare ogallrade."""
    klient = klient or _klient()
    forfragningar, bitar = {}, {}
    for sid, grupp in grupper.items():
        profil, annonser = grupp[0], grupp[1]
        regler = grupp[2] if len(grupp) > 2 else None
        for start in range(0, len(annonser), storlek):
            bit = annonser[start:start + storlek]
            cid = f"s{len(bitar)}"
            bitar[cid] = bit
            forfragningar[cid] = sall_forfragan(bit, profil, modell, regler)
    if not forfragningar:
        return {}
    import time
    batch = klient.messages.batches.create(
        requests=[{"custom_id": cid, "params": p} for cid, p in forfragningar.items()])
    print(f"  Sållning: {sum(len(b) for b in bitar.values())} annonser i {len(bitar)} delar skickade …")
    start = time.time()
    while klient.messages.batches.retrieve(batch.id).processing_status != "ended":
        if time.time() - start > 30 * 60:
            print("  Sållningen tog för lång tid – använder det som hann bli klart.")
            if not _avsluta_batch(klient, batch.id, 30):
                return {}
            break
        time.sleep(30)
    ut = {}
    for rad in klient.messages.batches.results(batch.id):
        if rad.result.type != "succeeded":
            continue
        bit = bitar[rad.custom_id]
        for nr, betyg in tolka_sallning(_text(rad.result.message), len(bit)).items():
            ut[bit[nr - 1].nyckel] = betyg
    print(f"  Sållning klar efter {round((time.time() - start) / 60)} min: {len(ut)} betygsatta.")
    return ut


def bedom_parallellt(uppgifter: list[tuple[str, Annons, str, str | None]], modell: str, klient=None,
                     tradar: int = 8) -> dict[str, tuple[int, str, str]]:
    """Vanliga anrop, flera samtidigt – reserv när batchen inte hinner. uppgifter: (id, annons, profil, regler)."""
    from concurrent.futures import ThreadPoolExecutor
    klient = klient or _klient()

    def en(u):
        cid, a, profil, regler = u
        try:
            return cid, bedom(a, profil, modell, klient, regler)
        except Exception as e:
            print(f"  Fel vid bedömning av {a.titel[:50]}: {e}")
            return cid, None
    # Kolla först med en enda: är krediterna slut finns ingen anledning att försöka 800 gånger.
    if uppgifter:
        cid, a, profil, regler = uppgifter[0]
        try:
            forsta = {cid: bedom(a, profil, modell, klient, regler)}
        except Exception as e:
            if "credit balance" in str(e).lower():
                raise SlutPaKrediter(str(e)) from e
            forsta = {}
        uppgifter = uppgifter[1:]
    with ThreadPoolExecutor(max_workers=tradar) as pool:
        return {**forsta, **{cid: r for cid, r in pool.map(en, uppgifter) if r}}


class SlutPaKrediter(RuntimeError):
    """Anthropic-kontot saknar krediter – inga bedömningar går att göra förrän det fyllts på."""


def bedom_grupper(kandidater: list, profil_for, regler_for, modell: str, klient=None,
                  storlek: int = GRUPPSTORLEK, max_vant: int = 40 * 60) -> dict[int, tuple[int, str, str]]:
    """Bedömer kandidaterna i grupper om `storlek` per spår, allt i en batch.
    Returnerar {index i kandidater: resultat}; det som saknas bedöms sedan en och en."""
    import time
    klient = klient or _klient()
    per_spar: dict[tuple, list[int]] = {}  # per spår OCH kategori – då delar gruppen samma korta profil
    for i, a in enumerate(kandidater):
        per_spar.setdefault((a.spar, a.kategori), []).append(i)
    grupper, forfragningar = {}, {}
    for sid, index in per_spar.items():
        for start in range(0, len(index), storlek):
            bit = index[start:start + storlek]
            cid = f"g{len(grupper)}"
            grupper[cid] = bit
            a0 = kandidater[bit[0]]
            forfragningar[cid] = grupp_forfragan([kandidater[i] for i in bit], profil_for(a0), modell, regler_for(a0))
    if not forfragningar:
        return {}
    batch = klient.messages.batches.create(
        requests=[{"custom_id": cid, "params": p} for cid, p in forfragningar.items()])
    print(f"  Batch {batch.id}: {len(kandidater)} annonser i {len(grupper)} grupper – väntar på svar …")
    start = time.time()
    while True:
        batch = klient.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        if time.time() - start > max_vant:
            print("  Batchen tog för lång tid – sparar det som hann bli klart och bedömer resten direkt.")
            if not _avsluta_batch(klient, batch.id, 30):
                return {}
            break
        time.sleep(30)
    ut = {}
    for rad in klient.messages.batches.results(batch.id):
        if rad.result.type == "errored" and "credit balance" in str(getattr(rad.result, "error", "")).lower():
            raise SlutPaKrediter(str(rad.result.error))
        if rad.result.type != "succeeded":
            continue
        bit = grupper[rad.custom_id]
        for nr, res in tolka_grupp(_text(rad.result.message), len(bit)).items():
            ut[bit[nr - 1]] = res
    print(f"  Batch klar efter {round((time.time() - start) / 60)} min: {len(ut)} av {len(kandidater)} bedömda.")
    return ut
