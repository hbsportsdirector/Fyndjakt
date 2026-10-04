"""Engångsverktyg: sparar rå HTML från nya källor så att läsarna kan skrivas mot verklig kod."""
import pathlib, requests
UT = pathlib.Path(__file__).parent.parent / "data" / "probe"
UT.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Fyndjakt; privat bevakning)", "Accept-Language": "sv-SE,sv;q=0.9"}
SIDOR = {
    "myrorna_annons0": "https://www.myrorna.se/shop/annons/teskedar-silver-stamplade-gab-silver-kattfot-5-st/",
    "myrorna_annons1": "https://www.myrorna.se/shop/annons/armring-sterling-silver-2/",
    "myrorna_annons_x": "https://www.myrorna.se/shop/annons/kandelabrar-tra-massing-1800-tal-samfraktas-ej/",
}
for namn, url in SIDOR.items():
    try:
        r = requests.get(url, headers=H, timeout=30)
        (UT / f"{namn}.html").write_text(f"<!-- {r.status_code} {r.url} -->\n" + r.text, encoding="utf-8")
        print(namn, r.status_code, len(r.text))
    except Exception as e:
        (UT / f"{namn}.html").write_text(f"<!-- FEL {e} -->", encoding="utf-8")
        print(namn, "FEL", e)
