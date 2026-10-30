"""Omvärdering av samlingen mot riktiga slutpriser på Auctionet.

För varje föremål söks avslutade auktioner med föremålets sökord. Värdet blir medianen av de sålda, räknat per
styck (partier delas med sitt antal). Står föremålets höjd i namnet eller anteckningen jämförs bara mot sålda i
ungefär samma storlek – en stor Stella Polaris-vas är inte en liten. Andelen som gick osåld redovisas, för den
säger hur lätt det är att få det sålt. Värdet uppdateras bara när det finns minst MIN_SALDA jämförelser;
annars ligger det gamla kvar och föremålet hamnar på listan "tunt underlag".

Körs av tools/vardera_samlingen.py (GitHub Actions, en gång i månaden).
"""
import re
from datetime import date

import prisjamforelse

MIN_SALDA = 3
STORLEK_TOLERANS = 0.25      # ±25 % av höjden …
STORLEK_MIN_CM = 3           # … men minst ±3 cm
UTAN_STORLEK = {"Konst", "Böcker", "Möbler"}   # mått där betyder annat (bredd × höjd, format)
MANADER = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


def hojd(text: str) -> float | None:
    """Höjden i cm ur en text: "höjd 25 cm", "H 25,5 cm", "25 cm hög", eller ett ensamt "Vas, 25 cm".
    Mått som "100×60 cm" och "Ø 20 cm" räknas inte som höjd."""
    t = (text or "").lower().replace(",", ".")
    m = re.search(r"(?:höjd|hojd|\bh)\s*[:.]?\s*(?:ca\.?|cirka)?\s*(\d{1,3}(?:\.\d)?)\s*cm", t) or \
        re.search(r"(\d{1,3}(?:\.\d)?)\s*cm\s+hög", t)
    if not m:
        ensamma = [x for x in re.finditer(r"(?<![×x*\d.])(\d{1,3}(?:\.\d)?)\s*cm", t)
                   if not re.search(r"(ø|diam|bredd|längd|djup|[×x*]\s*)$", t[max(0, x.start() - 8):x.start()].strip())]
        if len(ensamma) != 1 or re.search(r"\d\s*[×x*]\s*\d", t):
            return None
        m = ensamma[0]
    v = float(m.group(1))
    return v if 3 <= v <= 150 else None


def jamforbara(poster: list[dict], storlek: float | None) -> tuple[list[dict], bool]:
    """(poster, storleksfiltrerat). Med känd höjd: bara poster med höjd inom toleransen – om minst MIN_SALDA av
    dem är sålda. Annars alla (blandade storlekar)."""
    if not storlek:
        return poster, False
    marg = max(storlek * STORLEK_TOLERANS, STORLEK_MIN_CM)
    lika = [p for p in poster if (h := hojd(p["text"])) is not None and abs(h - storlek) <= marg]
    if sum(p["sald"] for p in lika) >= MIN_SALDA:
        return lika, True
    return poster, False


def _kr(n) -> str:
    return f"{int(round(n)):,}".replace(",", " ") + " kr"


def _datum(d: date) -> str:
    return f"{d.day} {MANADER[d.month - 1]} {d.year}"


def vardera(foremal: dict, poster: list[dict], idag: date | None = None) -> dict:
    """Värdering av ett föremål utifrån avslutade auktioner (prisjamforelse.avslutade)."""
    idag = idag or date.today()
    storlek = None if foremal.get("kategori") in UTAN_STORLEK else \
        hojd(f"{foremal.get('namn') or ''} {foremal.get('anteckning') or ''}")
    urval, filtrerat = jamforbara(poster, storlek)
    salda = [round(p["pris"] / prisjamforelse.styck_i(p["titel"])) for p in urval if p["sald"]]
    osalda = sum(1 for p in urval if not p["sald"])
    sammanfattning = prisjamforelse.sammanfatta(salda)
    andel_osald = round(osalda / len(urval), 2) if urval else None
    res = {"antal": len(salda), "osalda": osalda, "andel_osald": andel_osald, "storlek": storlek,
           "storleksfiltrerat": filtrerat, "uppdatera": bool(sammanfattning and len(salda) >= MIN_SALDA)}
    if sammanfattning:
        res.update({k: sammanfattning[k] for k in ("median", "lag", "hog")})
    res["text"] = text(res, idag)
    return res


def text(res: dict, idag: date) -> str:
    """Underlaget i en mening, t.ex. "Auctionet 30 okt 2026: 12 sålda, median 300 kr (250–350 kr), 55 % osålda –
    jämfört med föremål 19–31 cm höga." """
    if not res["uppdatera"]:
        delar = [f"Auctionet {_datum(idag)}: för få sålda ({res['antal']}) – värdet är inte ändrat"]
        if res["osalda"]:
            delar.append(f"{res['osalda']} osålda")
        return ", ".join(delar) + "."
    t = f"Auctionet {_datum(idag)}: {res['antal']} sålda, median {_kr(res['median'])} ({_kr(res['lag'])[:-3]}–{_kr(res['hog'])})"
    if res["andel_osald"]:
        t += f", {round(res['andel_osald'] * 100)} % osålda"
    if res["storleksfiltrerat"]:
        marg = max(res["storlek"] * STORLEK_TOLERANS, STORLEK_MIN_CM)
        t += f" – jämfört med föremål {round(res['storlek'] - marg)}–{round(res['storlek'] + marg)} cm höga"
    elif res["storlek"]:
        t += f" – för få i samma storlek ({res['storlek']:g} cm), blandade storlekar"
    return t + "."


MIN_SALDA_AUTO = 5                  # så många sålda krävs för att värdet ska ändras utan granskning
MAX_ANDRING = 2.0                   # nytt värde högst dubbla / minst halva det gamla – annars granskning
INTE_AUTO = {"Konst"}               # unika verk: samma konstnärs median säger lite om just det här verket
LAST = ("orört", "lås värde", "låst värde")   # står det i anteckningen rörs värdet aldrig automatiskt


OSAKER_ATTRIBUTION = ("trolig", "i stil med", "okänd", "kanske", "?")
INTE_SERIEORD = {"modell", "trolig", "serie", "nr"}


def _stammar(text: str) -> set[str]:
    return {o[:5] for o in prisjamforelse._ord(text.lower()) if len(o) >= 3 and not o.isdigit() and o not in INTE_SERIEORD}


def specifik(fras: str, foremal: dict) -> bool:
    """Gäller sökfrasen just det här föremålet? Den måste nämna tillverkaren/formgivaren eller serien – och har
    föremålet en serie måste serien vara med ("Vicke Lindstrand vas" jämför alla hans vaser, inte Stella Polaris)."""
    ord_ = {o[:5] for o in prisjamforelse._ord(fras)}
    serie = _stammar(str(foremal.get("serie") or ""))
    if serie:
        return bool(serie & ord_)
    return bool(_stammar(str(foremal.get("tillverkare") or "").replace("okänd", "")) & ord_)


def osaker_attribution(foremal: dict) -> bool:
    text = f"{foremal.get('tillverkare') or ''} {foremal.get('serie') or ''}".lower()
    return any(o in text for o in OSAKER_ATTRIBUTION)


def beslut(foremal: dict, res: dict, fras: str) -> tuple[bool, str]:
    """(ändra värdet automatiskt, skäl om inte). Allt som inte ändras automatiskt blir ett förslag att granska."""
    if not res["uppdatera"]:
        return False, f"för få sålda ({res['antal']})"
    if any(o in (foremal.get("anteckning") or "").lower() for o in LAST):
        return False, "värdet är låst i anteckningen"
    if foremal.get("kategori") in INTE_AUTO:
        return False, "konst – unika verk, jämför själv"
    if (foremal.get("antal") or 1) > 1:
        return False, f"parti om {foremal['antal']} – jämförelsen gäller ett styck"
    if osaker_attribution(foremal):
        return False, "osäker attribution (trolig/i stil med/okänd)"
    if not specifik(fras, foremal):
        return False, f"för allmänt sökord (\"{fras}\")"
    if res["antal"] < MIN_SALDA_AUTO:
        return False, f"bara {res['antal']} sålda"
    gammal = foremal.get("auk_median")
    if not gammal:
        return False, "inget tidigare värde att jämföra med"
    kvot = res["median"] / gammal
    if not (1 / MAX_ANDRING <= kvot <= MAX_ANDRING):
        return False, f"stor ändring (×{kvot:.1f}) – kontrollera"
    return True, ""


def foreslas(res: dict, skal: str) -> bool:
    """Blir värderingen ett förslag att granska på sajten? Inte för partier (jämförelsen gäller ett styck och
    vore missvisande), låsta värden eller när det inte finns något värde att föreslå."""
    return bool(res.get("uppdatera") and res.get("median")) and not skal.startswith(("parti", "värdet är låst"))


def sok_url(fras: str) -> str:
    from urllib.parse import quote
    return f"https://auctionet.com/sv/search?is=ended&q={quote(fras)}"
