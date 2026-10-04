"""Tester som körs helt offline: python -m pytest tests"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

import bedomning
import main
import notis
from databas import Databas
from sources import auctionet, tradera

FRAMTID = int(time.time()) + 86400

AUCTIONET_POST = {
    "id": 5420356, "currency": "SEK", "estimate": 2000, "state": "published",
    "title": 'BOKHYLLA, teak, "Varia bokhylla", AB Möbelfabriken Varia, Flen, 1950/60-tal.',
    "description": "<p>Bokhylla i teak med skåpsdel.\n<br />Höjd ca 210 cm, bredd ca 100 cm.</p>",
    "condition": "<p>Bruksslitage. Stötmärken, repor.</p>",
    "ends_at": FRAMTID, "location": "Norrtälje", "house": "Roslagens Auktionsverk",
    "url": "https://auctionet.com/en/5420356-bookcase-teak",
    "images": [{"w640": "https://images.auctionet.com/thumbs/w640_item_5420356_a.png", "hd": "x"}],
    "bids": [],
}


def test_auctionet_tolkning():
    a = auctionet.tolka(AUCTIONET_POST, "Möbler")
    assert a.nyckel == "auctionet:5420356"
    assert a.pris == 2000 and a.pris_text == "Utrop 2000 SEK"
    assert "<" not in a.beskrivning and "Skick: Bruksslitage" in a.beskrivning
    assert a.url.startswith("https://auctionet.com/sv/")
    assert a.plats == "Roslagens Auktionsverk, Norrtälje"
    assert a.bilder == ["https://images.auctionet.com/thumbs/w640_item_5420356_a.png"]


def test_auctionet_bud_och_avslutade():
    post = dict(AUCTIONET_POST, bids=[{"amount": 1500}, {"amount": 2600}])
    assert auctionet.tolka(post).pris == 2600
    assert auctionet.tolka(dict(AUCTIONET_POST, ends_at=1)) is None
    assert auctionet.tolka(dict(AUCTIONET_POST, state="ended")) is None


def test_tradera_tolkning_camel_och_pascal():
    camel = {"id": 123, "shortDescription": "Jordglob 1930-tal", "buyItNowPrice": 900,
             "thumbnailLink": "https://img/t.jpg", "itemLink": "https://www.tradera.com/item/1/123/x",
             "endDate": "2026-10-10T18:00:00Z"}
    a = tradera.tolka(camel, "Konst och dekor")
    assert a.titel == "Jordglob 1930-tal" and a.pris == 900 and a.bilder == ["https://img/t.jpg"]
    pascal = {"Id": 5, "ShortDescription": "Karta", "MaxBid": 300, "BuyItNowPrice": 800,
              "ImageLinks": ["https://img/1.jpg"]}
    b = tradera.tolka(pascal)
    assert b.pris == 300 and "köp nu 800" in b.pris_text and b.url.endswith("/item/5")
    assert tradera._poster({"items": [camel]}) == [camel]


def test_forfilter():
    cfg = {"uteslut_ord": ["ikea"], "max_pris": 1000}
    a = auctionet.tolka(AUCTIONET_POST)
    assert "pris" in main.forfiltrera(a, cfg)
    a.pris = 500
    assert main.forfiltrera(a, cfg) is None
    a.titel += " IKEA"
    assert "ikea" in main.forfiltrera(a, cfg)


def test_tolka_ai_svar():
    assert bedomning.tolka_svar('{"betyg": 8, "motivering": "Mörk valnöt."}') == (8, "Mörk valnöt.")
    assert bedomning.tolka_svar('Här: {"betyg": "9", "motivering": "x"}')[0] == 9
    assert bedomning.tolka_svar("nonsens")[0] == 0


def test_bedom_skickar_bilder_och_stil():
    anrop = {}

    class Falsk:
        class messages:
            @staticmethod
            def create(**kw):
                anrop.update(kw)
                return SimpleNamespace(content=[SimpleNamespace(text='{"betyg":7,"motivering":"ok"}')])

    a = auctionet.tolka(AUCTIONET_POST)
    assert bedomning.bedom(a, "MIN STIL", "modell-x", Falsk) == (7, "ok")
    assert "MIN STIL" in anrop["system"]
    delar = anrop["messages"][0]["content"]
    assert delar[0]["type"] == "image" and delar[0]["source"]["type"] == "url"


def test_notistext_escapar_html():
    a = auctionet.tolka(dict(AUCTIONET_POST, title="Lampa <mässing> & glas"))
    t = notis.formatera(a, 8, "Passar <bra>")
    assert "&lt;mässing&gt; &amp;" in t and "&lt;bra&gt;" in t and "8/10" in t


def test_databas_och_traffar(tmp_path):
    db = Databas(tmp_path / "t.db")
    bra = auctionet.tolka(AUCTIONET_POST, "Möbler")
    dalig = auctionet.tolka(dict(AUCTIONET_POST, id=2), "Möbler")
    gammal = auctionet.tolka(dict(AUCTIONET_POST, id=3), "Möbler")
    gammal.slutar_ts = 1
    assert not db.finns(bra.nyckel)
    db.spara(bra, 8, "m", True)
    db.spara(dalig, 3, "nej")
    db.spara(gammal, 9, "utgången")
    assert db.finns(bra.nyckel)
    t = db.traffar(6)
    assert [r["nyckel"] for r in t] == [bra.nyckel]
    assert t[0]["bilder"] == bra.bilder and t[0]["kategori"] == "Möbler"
    db.rensa_gamla()
    assert db.finns(bra.nyckel)


def test_gammal_databas_migreras(tmp_path):
    import sqlite3
    f = tmp_path / "old.db"
    con = sqlite3.connect(f)
    con.execute("CREATE TABLE sedda (nyckel TEXT PRIMARY KEY, titel TEXT, url TEXT, betyg INTEGER, motivering TEXT, notifierad INTEGER DEFAULT 0, sedd TEXT DEFAULT CURRENT_TIMESTAMP)")
    con.execute("INSERT INTO sedda (nyckel, titel, url, betyg, motivering) VALUES ('x:1','t','u',8,'m')")
    con.commit(); con.close()
    db = Databas(f)
    assert db.finns("x:1") and db.traffar(6)[0]["bilder"] == []


def test_sajt_byggs(tmp_path, monkeypatch):
    import sajt
    monkeypatch.setattr(sajt, "UT", tmp_path)
    monkeypatch.setattr(sajt, "ROT", tmp_path.parent)
    db = Databas(tmp_path / "t.db")
    db.spara(auctionet.tolka(dict(AUCTIONET_POST, title="Lampa </script><b>"), "Belysning"), 9, "Mässing")
    html = sajt.bygg(db, {"sokningar": {"Belysning": []}, "min_betyg": 7}).read_text(encoding="utf-8")
    assert "__DATA__" not in html and "Mässing" in html
    assert "</script><b>" not in html  # ingen injektion i inbäddad data


def test_config_laddas():
    cfg = main.las_config()
    hem, saml = cfg["spar"]["hemmet"], cfg["spar"]["samlingen"]
    assert "Obsidian Green" in hem["profil"]            # från stil.md
    assert "Viktigt vid bedömningen" in hem["profil"]   # från tillagg
    assert "HAR REDAN" in hem["profil"] and "Chesterfield" in hem["profil"]
    assert "Kartor, glober och kuriosa" in hem["sokningar"]
    assert "Evert Lundquist" in saml["profil"]          # från samlingsprofil.md
    assert "Glas" in saml["sokningar"]


def test_utlandsk_valuta_raknas_om():
    a = auctionet.tolka(dict(AUCTIONET_POST, currency="GBP", estimate=100))
    assert a.pris == 1300 and "≈ 1 300 kr" in a.pris_text


def test_blanda_kategorier():
    ann = [auctionet.tolka(dict(AUCTIONET_POST, id=i), k) for i, k in
           enumerate(["Möbler", "Möbler", "Möbler", "Belysning", "Konst och dekor"])]
    assert [a.kategori for a in main.blanda_kategorier(ann)[:3]] == ["Möbler", "Belysning", "Konst och dekor"]


def test_har_redan_och_bara_sverige():
    cfg = {"bara_sverige": True, "max_pris": 1000}
    spar = {"har_redan_ord": ["chesterfield"], "max_pris": 5000}
    a = auctionet.tolka(AUCTIONET_POST)  # 2000 kr: över gemensam gräns, under spårets
    assert main.forfiltrera(a, cfg, spar) is None
    assert "pris" in main.forfiltrera(a, cfg)
    a.titel = "SOFFA, Chesterfield"
    assert "har redan" in main.forfiltrera(a, cfg, spar)
    b = auctionet.tolka(dict(AUCTIONET_POST, currency="DKK"))
    assert "utanför Sverige" in main.forfiltrera(b, cfg, spar)


def test_sajt_max_per_sokord(tmp_path, monkeypatch):
    import sajt, json, re
    monkeypatch.setattr(sajt, "UT", tmp_path)
    db = Databas(tmp_path / "t.db")
    for i in range(5):
        a = auctionet.tolka(dict(AUCTIONET_POST, id=i), "Konst")
        a.sokord = "persisk matta" if i < 4 else "jordglob"
        db.spara(a, 9, "x")
    html = sajt.bygg(db, {"sokningar": {}, "sajt_min_betyg": 8, "sajt_max_per_sokord": 2}).read_text(encoding="utf-8")
    data = json.loads(re.search(r"const D = (.*?);\n", html).group(1))
    assert len(data["poster"]) == 3


def test_sajt_har_flikar_per_spar(tmp_path, monkeypatch):
    import sajt, json, re
    monkeypatch.setattr(sajt, "UT", tmp_path)
    db = Databas(tmp_path / "t.db")
    for i, sp in enumerate(["hemmet", "samlingen", "samlingen"]):
        a = auctionet.tolka(dict(AUCTIONET_POST, id=i), "Glas")
        a.spar, a.sokord = sp, f"s{i}"
        db.spara(a, 9, "x")
    cfg = {"sajt_min_betyg": 8, "spar": {"hemmet": {"namn": "The Reading Room", "sokningar": {"Möbler": []}},
                                         "samlingen": {"namn": "Samlingen", "sokningar": {"Glas": []}}}}
    data = json.loads(re.search(r"const D = (.*?);\n", sajt.bygg(db, cfg).read_text(encoding="utf-8")).group(1))
    assert [s["namn"] for s in data["spar"]] == ["The Reading Room", "Samlingen"]
    assert sorted(p["spar"] for p in data["poster"]) == ["hemmet", "samlingen", "samlingen"]


# ── Nya källor, testade mot riktig HTML som hämtats från sajterna ──
FIX = Path(__file__).parent / "fixtures"
FAST_TID = 1791000000  # före alla sluttider i fixturerna


def _las(namn):
    return (FIX / f"{namn}.html").read_text(encoding="utf-8")


def test_bukowskis(monkeypatch):
    from sources import bukowskis
    monkeypatch.setattr(bukowskis.time, "time", lambda: FAST_TID)
    r = bukowskis.tolka_sida(_las("bukowskis"), "Test")
    assert len(r) == 73
    sek = next(a for a in r if a.id == "1742747")
    assert sek.titel.startswith("Hans Lyberg") and sek.pris == 3800 and sek.valuta == "SEK"
    assert sek.url.endswith("/sv/lots/1742747-hans-lyberg-bagare-silver-boras-1811")
    assert sek.bilder[0].startswith("https://") and sek.slutar_ts
    eur = next(a for a in r if a.valuta == "EUR")
    assert "≈" in eur.pris_text
    monkeypatch.setattr(bukowskis.time, "time", lambda: 9e12)
    assert bukowskis.tolka_sida(_las("bukowskis")) == []  # utgångna sorteras bort


def test_myrorna(monkeypatch):
    from sources import myrorna
    monkeypatch.setattr(myrorna.time, "time", lambda: FAST_TID)
    r = myrorna.tolka_sida(_las("myrorna"), "Test")
    assert len(r) == 50
    a = r[0]
    assert a.id == "500523" and a.pris == 249 and "Ledande bud" in a.pris_text
    assert a.url.startswith("https://www.myrorna.se/shop/annons/") and a.bilder and a.slutar_ts


def test_stadsmissionen(monkeypatch):
    from sources import stadsmissionen
    r = stadsmissionen.tolka_sida(_las("stadsmissionen"))
    assert len(r) == 16 and all(a.pris and a.url.startswith("https://www.stadsmissionen.se/shop/produkt/") for a in r)
    assert not any(a.titel.startswith("Okänt märke") for a in r)
    monkeypatch.setattr(stadsmissionen, "_katalog", r)
    traffar = [a.titel for a in stadsmissionen.sok("skål blå", "Glas")]
    assert "Ljusgrön skål med blå fot" in traffar and len(traffar) < 5
    assert stadsmissionen.sok("skål blå", "Glas")[0].kategori == "Glas"
    assert stadsmissionen.sok("jordglob") == []


def test_stadsmissionen_huvudord():
    from sources import stadsmissionen
    from sources import Annons
    a = Annons(kalla="stadsmissionen", id="x", titel="Bokhylla i furu", url="u")
    assert stadsmissionen.matchar("bokhylla valnöt", a)
    assert not stadsmissionen.matchar("Erik Höglund", Annons(kalla="s", id="y", titel="Erik Johansson vas", url="u"))
    assert not stadsmissionen.matchar("byst brons", Annons(kalla="s", id="z", titel="Bysthållare", url="u"))


def test_blanda_varvar_kallor():
    ann = [auctionet.tolka(dict(AUCTIONET_POST, id=i), "Möbler") for i in range(5)]
    from sources import Annons
    ann.append(Annons(kalla="myrorna", id="m", titel="t", url="u", kategori="Möbler"))
    assert "myrorna" in [a.kalla for a in main.blanda_kategorier(ann)[:2]]


def test_region():
    import sajt
    assert sajt.region_for("auctionet", "Roslagens Auktionsverk, Norrtälje") == ("Norrtälje", "Stockholm")
    assert sajt.region_for("auctionet", "Kalmar Auktionsverk, Kalmar")[1] == "Östergötland, Småland och Blekinge"
    assert sajt.region_for("auctionet", "Hus, Gothenburg")[1] == "Västsverige och Värmland"
    assert sajt.region_for("auctionet", "Hus, Okändstad")[1] == "Övriga Sverige"
    assert sajt.region_for("stadsmissionen", "x")[1] == "Stockholm"
    assert sajt.region_for("myrorna", "x")[1] == "Webbutik med frakt"
