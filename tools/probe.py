"""Engångsverktyg: sparar rå HTML från nya källor så att läsarna kan skrivas mot verklig kod."""
import pathlib, requests
UT = pathlib.Path(__file__).parent.parent / "data" / "probe"
UT.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Fyndjakt; privat bevakning)", "Accept-Language": "sv-SE,sv;q=0.9"}
SIDOR = {
    "ssm_sok_hem": "https://www.stadsmissionen.se/shop/hem?search_text=glas",
    "ssm_sok_alla": "https://www.stadsmissionen.se/shop?search_text=kosta",
    "ssm_sok_hem_p1": "https://www.stadsmissionen.se/shop/hem?search_text=glas&page=1",
    "bukowskis_sok_stor": "https://www.bukowskis.com/sv/lots/search/silver",
    "bukowskis_sok_stor_p2": "https://www.bukowskis.com/sv/lots/page/2/search/silver",
}
for namn, url in SIDOR.items():
    try:
        r = requests.get(url, headers=H, timeout=30)
        (UT / f"{namn}.html").write_text(f"<!-- {r.status_code} {r.url} -->\n" + r.text, encoding="utf-8")
        print(namn, r.status_code, len(r.text))
    except Exception as e:
        (UT / f"{namn}.html").write_text(f"<!-- FEL {e} -->", encoding="utf-8")
        print(namn, "FEL", e)
