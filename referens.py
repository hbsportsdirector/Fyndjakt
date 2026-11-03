"""Referensbiblioteket för stämplar: tolkar en såld Auctionet-post till en referensrad.

Auktionshusen skriver formgivaren i versaler först i titeln ("MARI SIMMULSON. Skålfat, keramik, Upsala-Ekeby.")
och vad som står på botten i katalogtexten ("Märkt Mari Simmulsson, Upsala-Ekeby 1067", "Signed. Model No. 2084").
Sista bilden är nästan alltid botten/stämpeln. Ur det plockas fabrik, formgivare, modellnummer och stämpelfras –
det som Butik sedan slår upp när en stämpel lästs, för att visa Claude riktiga referensfoton i stället för minne.
"""
import re
from datetime import datetime, timezone

# Fabriker: mönster → namn. Ordningen spelar roll när flera matchar (första vinner).
FABRIKER = [
    (r"up+sala[\s-]*ekeby|\bekeby\b|\bUE\b", "Upsala-Ekeby"),
    (r"gusta[fv]sberg", "Gustavsberg"),
    (r"r[öo]rstrand", "Rörstrand"),
    (r"\barabia\b", "Arabia"),
    (r"royal copenhagen|kongelig porcel|\bkgl\.? porcel", "Royal Copenhagen"),
    (r"bing\s*&\s*gr[øo]ndahl|\bb\s*&\s*g\b", "Bing & Grøndahl"),
    (r"\bsaxbo\b", "Saxbo"),
    (r"palshus", "Palshus"),
    (r"k[äa]hler", "Kähler"),
    (r"bo ?fajans|\bbo\b[^.]{0,20}g[äa]vle", "Bo Fajans"),
    (r"\bgefle\b", "Gefle"),
    (r"h[öo]gan[äa]s", "Höganäs"),
    (r"\blaholm\b", "Laholm"),
    (r"nittsj[öo]", "Nittsjö"),
    (r"tilgmans", "Tilgmans"),
    (r"\bjie\b|gantofta", "Jie Gantofta"),
    (r"karlskrona", "Karlskrona"),
    (r"aling[s]?[åa]s", "Alingsås"),
    (r"\bboda\b", "Boda"),
    (r"\bkosta\b", "Kosta"),
    (r"orrefors", "Orrefors"),
    (r"gullaskruf", "Gullaskruf"),
    (r"\bålems?\b|alems?glas", "Åfors"),
    (r"\bafors\b|åfors", "Åfors"),
    (r"strömbergshyttan|str[öo]mberg", "Strömbergshyttan"),
    (r"reijmyre", "Reijmyre"),
    (r"\bnuutaj[äa]rvi|notsj[öo]", "Nuutajärvi"),
    (r"\biittala\b", "Iittala"),
    (r"\bholmegaard", "Holmegaard"),
]

# Kända formgivare – används för att känna igen dem i texten och för att normalisera stavning.
FORMGIVARE = [
    "Mari Simmulson", "Ingrid Atterberg", "Anna-Lisa Thomson", "Vicke Lindstrand", "Hjördis Oldfors", "Sven-Erik Skawonius",
    "Dorothy Clough", "Taisto Kaasinen", "Harald Östergren", "Eva Jancke-Björk", "Stig Lindberg", "Berndt Friberg", "Lisa Larson",
    "Wilhelm Kåge", "Karin Björquist", "Bibi Breger", "Gunnar Nylund", "Hertha Bengtson", "Carl-Harry Stålhane", "Marianne Westman",
    "Sylvia Leuchovius", "Olle Alberius", "Inger Persson", "Louise Adelborg", "Edvin Öhrström", "Erik Höglund", "Bertil Vallien",
    "Ulrica Hydman-Vallien", "Kjell Engman", "Nils Landberg", "Simon Gate", "Edward Hald", "Sven Palmqvist", "Ingeborg Lundin",
    "Gunnar Cyrén", "Carl Fagerlund", "Kaj Franck", "Birger Kaipiainen", "Oiva Toikka", "Timo Sarpaneva", "Tapio Wirkkala",
    "Arthur Percy", "Axel Salto", "Per Linnemann-Schmidt", "Nathalie Krebs", "Eva Stæhr-Nielsen", "Edgar Böckman",
    "Ewald Dahlskog", "Allan Ebeling", "John Andersson", "Thomas Hellström", "Jerk Werkmäster", "Nils Thorsson", "Jørgen Mogensen",
    "Gertrud Vasegaard", "Knud Kyhn", "Bode Willumsen", "Gunnar Wennerberg", "Alf Wallander", "Ewald Dahlskog", "Gösta Grähs",
    "Kjell Blomberg", "Arthur Carlsson Percy", "Bengt Edenfalk", "Paul Hoff", "Lillemor Mannerheim", "Carl Larsson",
]
_ALIAS = {"mari simmulsson": "Mari Simmulson", "mari simulsson": "Mari Simmulson", "mari simulson": "Mari Simmulson",
          "maris": "Mari Simmulson", "arthur carlsson percy": "Arthur Percy", "carl harry stålhane": "Carl-Harry Stålhane",
          "anna lisa thomson": "Anna-Lisa Thomson", "sven erik skawonius": "Sven-Erik Skawonius", "ulrica hydman vallien": "Ulrica Hydman-Vallien",
          "lisa larsson": "Lisa Larson", "eva staehr nielsen": "Eva Stæhr-Nielsen", "eva stæhr nielsen": "Eva Stæhr-Nielsen",
          "stig lindbergh": "Stig Lindberg", "bernt friberg": "Berndt Friberg", "berndt fridberg": "Berndt Friberg", "gunnar nylund": "Gunnar Nylund",
          "herta bengtson": "Hertha Bengtson", "hertha bengtsson": "Hertha Bengtson", "carl harry stalhane": "Carl-Harry Stålhane",
          "vicke lindstrand": "Vicke Lindstrand", "viktor lindstrand": "Vicke Lindstrand", "eric höglund": "Erik Höglund",
          # Stavningsvarianter som förekommer i auktionshusens kataloger (hittade i biblioteket 2026-11-03).
          "gunnar nylynd": "Gunnar Nylund", "carl harry ståhlhane": "Carl-Harry Stålhane", "bertil valien": "Bertil Vallien", "marianne westmann": "Marianne Westman",
          "ulrika hydman vallien": "Ulrica Hydman-Vallien", "mari simmulsen": "Mari Simmulson", "anna lisa thompson": "Anna-Lisa Thomson", "anna lisa thomsson": "Anna-Lisa Thomson",
          "anna lisa thompsson": "Anna-Lisa Thomson", "ingrid atteberg": "Ingrid Atterberg", "karin björqvist": "Karin Björquist", "lillemor mannheimer": "Lillemor Mannerheim",
          "hjördis oldsfors": "Hjördis Oldfors", "göran wärf": "Göran Wärff", "nils thorson": "Nils Thorsson", "ulla procope": "Ulla Procopé", "taisto kaasien": "Taisto Kaasinen",
          "sven wejsfeldt": "Sven Wejsfelt", "eva jancke björck": "Eva Jancke-Björk", "eva janke björk": "Eva Jancke-Björk", "helmer ringstöm": "Helmer Ringström",
          "per linneman schmidt": "Per Linnemann-Schmidt", "allan eberling": "Allan Ebeling", "jerk werkmeister": "Jerk Werkmäster", "jerk werkmester": "Jerk Werkmäster",
          "signe persson melin": "Signe Persson-Melin", "erik morsnils": "Erik Mornils", "olle brozen": "Olle Brozén", "olle bronzén": "Olle Brozén", "lars thoren": "Lars Thorén",
          "olof larson": "Olof Larsson", "mona morales schildt": "Mona Morales-Schildt", "dorothy clogh": "Dorothy Clough"}
# Ord i en versal titelinledning som betyder "föremål", inte "person": "TEA SET, 24 parts", "SKÅLAR/FAT, stengods".
OBJEKTORD = set("""vas vaser vase vases skål skålar bowl bowls fat dish dishes plate plates tallrik tallrikar figurin figuriner figurine
figurines figur figurer figure figures skulptur skulpturer sculpture sculptures urna urnor urn kruka krukor pot pots kanna kannor jug pitcher
lampa lampor lamp lampfot askfat ashtray servis service set tea coffee kaffeservis matservis servisdelar delar parts parti lot glas glass
glasföremål keramik ceramic ceramics stengods stoneware porslin porcelain fajans faience flintgods earthenware karaff karaffer decanter
ljusstake ljusstakar candlestick candlesticks väggplatta väggrelief relief platta plattor tile tiles skulpturer burk burkar jar jars
kopp koppar cup cups mugg muggar mug mugs tekanna teapot bricka tray föremål objekt items pieces samling collection konstglas art
krus tappkran kannor med och and with samt par pair bokstöd ljuslykta lykta fönsterfat väggur klocka dosa dosor ask askar skrin""".split())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("-", " ")).strip()


_FORMGIVARE_NORM = {_norm(f): f for f in FORMGIVARE}
_FORMGIVARE_NORM.update({_norm(k): v for k, v in _ALIAS.items()})

STAMPEL = re.compile(
    r"(st[äa]mpl\w*|st[äa]mpel\w*|signer\w*|signed|sign\.|signatur\w*|m[äa]rkt|mærket|marked|monogram\w*|etikett\w*|label\w*|"
    r"pr[äa]glad|impressed|ristad|incised|inskr\w*|numrerad|numbered|modellnummer|model(?:l)?\s*(?:no|nr)\.?|dekornummer)"
    r"[^.;]{0,100}", re.I)
# Modellnummer: "nr 342", "Model No. 2084", "1034/9", "UE 1067", "modell 4145". Inte årtal.
MODELL = re.compile(r"(?:\bnr\.?|\bno\.?|\bn:o|modell(?:nummer)?|model(?:l)?(?:\s*no\.?)?|dekor|form(?:nr|nummer)?|#|\bUE)\s*\.?\s*(\d{3,5}(?:[/-]\d{1,4})?|\d{2}/\d{1,4})\b", re.I)
# Parti: flera föremål i samma post – sista bilden är då inte säkert stämpeln på det namngivna föremålet.
PARTI = re.compile(r"\b(parti|delar|parts|pieces|\d+\s*st\b|stycken|bland annat|bl\.?\s?a\.?|\d+\s*(?:vaser|skålar|fat|figuriner|delar|tallrikar|koppar))\b|\b(?:samt|och|and)\s+[A-ZÅÄÖ]{3,}", re.I)
MODELL_SNED = re.compile(r"\b(\d{3,4}/\d{1,4})\b")
ARTAL = re.compile(r"^(18[5-9]\d|19\d\d|20[0-3]\d)$")   # årtal 1850–2039 är inte modellnummer
FABRIK_NR = re.compile(r"(?:ekeby|gusta[fv]sberg|r[öo]rstrand|gefle|h[öo]gan[äa]s|laholm|nittsj[öo]|bo ?fajans|karlskrona|tilgmans|kosta|boda)\s+(?:sweden\s+)?(\d{3,5}(?:[/-]\d{1,4})?)\b", re.I)
LOST_NR = re.compile(r"\b(\d{3,4})\b(?!\s*(?:cm|mm|x|×|kr|st\b|delar|%))")
TITEL_NAMN = re.compile(r"^\s*([A-ZÅÄÖØÆÉÜ][A-ZÅÄÖØÆÉÜ'`-]+(?:\s+[A-ZÅÄÖØÆÉÜ][A-ZÅÄÖØÆÉÜ'`-]+){1,3})\s*[.,:]")


def ren(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "").replace("&amp;", "&").replace("&nbsp;", " ")).strip()


def fabrik_i(text: str) -> str | None:
    for monster, namn in FABRIKER:
        if re.search(monster, text, re.I):
            return namn
    return None


def formgivare_i(titel: str, text: str) -> str | None:
    """Ur titelns inledande versaler först ("MARI SIMMULSON. Skålfat …"), annars ett känt namn någonstans i texten."""
    m = TITEL_NAMN.match(titel or "")
    if m:
        namn = m.group(1)
        if not fabrik_i(namn) and not any(w.strip("'`") in OBJEKTORD for w in namn.lower().replace("-", " ").split()):
            n = _norm(namn)
            return _FORMGIVARE_NORM.get(n) or " ".join(w.capitalize() if "-" not in w else "-".join(x.capitalize() for x in w.split("-")) for w in namn.lower().split())
    allt = _norm((titel or "") + " " + (text or ""))
    for n, namn in sorted(_FORMGIVARE_NORM.items(), key=lambda kv: -len(kv[0])):
        if n in allt:
            return namn
    return None


def stampeltext_i(text: str) -> str:
    delar = []
    for m in STAMPEL.finditer(text or ""):
        fras = m.group(0).strip(" ,")
        if fras and fras not in delar:
            delar.append(fras)
    return "; ".join(delar)[:240]


def modell_i(stampeltext: str, text: str) -> str | None:
    """Modellnummer: helst ur stämpelfrasen, annars ur texten; snedstrecksnummer (1034/9) räknas alltid. Aldrig ett årtal."""
    for kalla in (stampeltext, text):
        for m in MODELL_SNED.finditer(kalla or ""):
            return m.group(1)
        for monster in (MODELL, FABRIK_NR):
            for m in monster.finditer(kalla or ""):
                n = m.group(1)
                if not ARTAL.match(re.split(r"[/-]", n)[0]):
                    return n
    # Sista utvägen: ett ensamt tre-/fyrsiffrigt tal i själva stämpelfrasen (inte i beskrivningen, där måtten står).
    for m in LOST_NR.finditer(stampeltext or ""):
        if not ARTAL.match(m.group(1)):
            return m.group(1)
    return None


def tolka_post(post: dict, sokfras: str = "") -> dict | None:
    """En Auctionet-post (API v2) → referensrad, eller None om den saknar bild eller inte går att placera på en fabrik."""
    titel = ren(post.get("title", ""))
    text = ren(post.get("description", ""))
    skick = ren(post.get("condition", ""))
    bilder = [b.get("w640") or b.get("hd") for b in (post.get("images") or []) if b.get("w640") or b.get("hd")]
    if not bilder or not post.get("id"):
        return None
    fabrik = fabrik_i(titel) or fabrik_i(text) or fabrik_i(sokfras)
    if not fabrik:
        return None
    allt = f"{text} {skick}"
    stampeltext = stampeltext_i(allt)
    bud = [b.get("amount") or 0 for b in (post.get("bids") or [])]
    pris = post.get("highest_bid") or (max(bud) if bud else 0) or None
    slutade = datetime.fromtimestamp(post["ends_at"], timezone.utc).date().isoformat() if post.get("ends_at") else None
    url = (post.get("url") or "").replace("auctionet.com/en/", "auctionet.com/sv/") or f"https://auctionet.com/sv/{post['id']}"
    return {
        "kalla": "auctionet", "kalla_id": str(post["id"]), "titel": titel[:200], "fabrik": fabrik,
        "formgivare": formgivare_i(titel, allt), "modell": modell_i(stampeltext, allt), "stampeltext": stampeltext or None,
        "text": (text + (" Skick: " + skick if skick else ""))[:600],
        "bild_url": bilder[-1], "bilder": bilder[:8], "url": url, "pris": int(pris) if pris else None,
        "salt": post.get("state") == "sold" and bool(pris), "slutade": slutade, "sokfras": sokfras[:80] or None,
        "hus": (post.get("house") or "")[:80] or None,
        "parti": bool(PARTI.search(titel)) or (post.get("antal") or 1) > 1,
    }
