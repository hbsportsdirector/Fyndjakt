"""Engångsverktyg: sparar rå HTML från nya källor så att läsarna kan skrivas mot verklig kod."""
import pathlib, requests
UT = pathlib.Path(__file__).parent.parent / "data" / "probe"
UT.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Fyndjakt; privat bevakning)", "Accept-Language": "sv-SE,sv;q=0.9"}
SIDOR = {
    "bukowskis_sok": "https://www.bukowskis.com/sv/lots/search/bokhylla",
    "bukowskis_sok2": "https://www.bukowskis.com/sv/lots/search/erik%20h%C3%B6glund",
    "bukowskis_lot": "https://www.bukowskis.com/sv/lots/1745512-bokhylla-med-skap-funkis-1930-tal",
    "myrorna_sok": "https://www.myrorna.se/shop/?s=silver",
    "myrorna_sok_p2": "https://www.myrorna.se/shop/sida/2/?s=glas",
    "stadsmissionen_hem": "https://www.stadsmissionen.se/shop/hem",
    "stadsmissionen_vintage": "https://www.stadsmissionen.se/shop/premium-vintage",
    "stadsmissionen_hem_p2": "https://www.stadsmissionen.se/shop/hem?page=2",
}
for namn, url in SIDOR.items():
    try:
        r = requests.get(url, headers=H, timeout=30)
        (UT / f"{namn}.html").write_text(f"<!-- {r.status_code} {r.url} -->\n" + r.text, encoding="utf-8")
        print(namn, r.status_code, len(r.text))
    except Exception as e:
        (UT / f"{namn}.html").write_text(f"<!-- FEL {e} -->", encoding="utf-8")
        print(namn, "FEL", e)
