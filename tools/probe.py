"""Felsökning: Myrornas sök verkar ignorera ?s= – spara rå-HTML och prova några varianter."""
import json, pathlib, re, requests
UT = pathlib.Path(__file__).parent.parent / "data" / "probe"
UT.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Fyndjakt; privat bevakning)", "Accept-Language": "sv-SE,sv;q=0.9"}
B = "https://www.myrorna.se"
ut = {}
forsok = {
    "shop_s": f"{B}/shop/?s=vas",
    "root_s": f"{B}/?s=vas",
    "root_s_auction": f"{B}/?s=vas&post_type=auction",
    "root_s_product": f"{B}/?s=vas&post_type=product",
    "shop_sok": f"{B}/shop/?sok=vas",
    "shop_search": f"{B}/shop/?search=vas",
    "shop_q": f"{B}/shop/?q=vas",
    "wp_search": f"{B}/wp-json/wp/v2/search?search=vas&per_page=20",
    "wp_types": f"{B}/wp-json/wp/v2/types",
    "nyast": f"{B}/shop/?orderby=date",
    "nyast2": f"{B}/shop/?sort=newest",
    "hem": f"{B}/shop/kategori/hem-prylar/",
}
for namn, url in forsok.items():
    try:
        r = requests.get(url, headers=H, timeout=30)
        t = r.text
        titlar = re.findall(r'/shop/annons/([^/"]+)/', t)
        ut[namn] = {"status": r.status_code, "url": r.url, "langd": len(t),
                    "annonser": list(dict.fromkeys(titlar))[:8],
                    "borjan": t[:300] if "json" in url else ""}
        if namn in ("shop_s", "wp_types"):
            (UT / f"myrorna_{namn}.html").write_text(t, encoding="utf-8")
    except Exception as e:
        ut[namn] = {"fel": str(e)[:200]}
# Sökformulär, sorteringsval och skript som anropar något sök-API
html = (UT / "myrorna_shop_s.html").read_text(encoding="utf-8") if (UT / "myrorna_shop_s.html").exists() else ""
ut["formular"] = re.findall(r"<form[^>]*>.*?</form>", html, re.S)[:5]
ut["select"] = re.findall(r"<select[^>]*>.*?</select>", html, re.S)[:3]
ut["ajax"] = sorted(set(re.findall(r"(?:admin-ajax\.php|wp-json/[\w/\-]+|algolia|search[\w\-/]*\.js|api/[\w/\-]+)", html)))[:30]
ut["datattr"] = sorted(set(re.findall(r'data-(?:sort|search|orderby|filter)[\w-]*="[^"]*"', html)))[:30]
(UT / "myrorna.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(ut, ensure_ascii=False)[:3000])
