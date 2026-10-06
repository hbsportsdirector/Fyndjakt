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
    pascal = {"Id": 5, "ShortDescription": "Karta", "MaxBid": 300, "BuyItNowPrice": 800, "HasBids": True,
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
    assert bedomning.tolka_svar('{"betyg": 8, "motivering": "Mörk valnöt.", "jamforsok": "bokskåp valnöt"}') == (8, "Mörk valnöt.", "bokskåp valnöt")
    assert bedomning.tolka_svar('{"betyg": 8, "motivering": "x"}') == (8, "x", "")
    assert bedomning.tolka_svar('Här: {"betyg": "9", "motivering": "x"}')[0] == 9
    assert bedomning.tolka_svar("nonsens")[0] == 0


def test_bedom_skickar_bilder_och_stil():
    anrop = {}

    class Falsk:
        class messages:
            @staticmethod
            def create(**kw):
                anrop.update(kw)
                return SimpleNamespace(content=[SimpleNamespace(text='{"betyg":7,"motivering":"ok","jamforsok":"teak bokhylla"}')])

    a = auctionet.tolka(AUCTIONET_POST)
    assert bedomning.bedom(a, "MIN STIL", "modell-x", Falsk) == (7, "ok", "teak bokhylla")
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
    cfg = {"min_betyg": 7, "_admins": {"per"}, "spar": {"hemmet": {"namn": "H", "sokningar": {"Belysning": []}}}}
    for r in db.traffar(0):
        pass
    db.con.execute("UPDATE sedda SET spar='hemmet'"); db.con.commit()
    html = sajt.bygg(db, cfg).read_text(encoding="utf-8")
    assert "__DATA__" not in html
    assert "Mässing" not in html and "Lampa" not in html  # inga fynd i den publika sidan
    assert sajt.anvandarfynd(db, cfg)["per"]["poster"][0]["motivering"] == "Mässing"


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
    db.con.execute("UPDATE sedda SET spar='hemmet'"); db.con.commit()
    cfg = {"_admins": {"per"}, "sajt_min_betyg": 8, "sajt_max_per_sokord": 2, "spar": {"hemmet": {"sokningar": {}}}}
    assert len(sajt.anvandarfynd(db, cfg)["per"]["poster"]) == 3


def test_sajt_har_flikar_per_spar(tmp_path, monkeypatch):
    import sajt, json, re
    monkeypatch.setattr(sajt, "UT", tmp_path)
    db = Databas(tmp_path / "t.db")
    for i, sp in enumerate(["hemmet", "samlingen", "samlingen"]):
        a = auctionet.tolka(dict(AUCTIONET_POST, id=i), "Glas")
        a.spar, a.sokord = sp, f"s{i}"
        db.spara(a, 9, "x")
    cfg = {"sajt_min_betyg": 8, "_admins": {"per"}, "spar": {"hemmet": {"namn": "The Reading Room", "sokningar": {"Möbler": []}},
                                         "samlingen": {"namn": "Samlingen", "sokningar": {"Glas": []}}}}
    data = sajt.anvandarfynd(db, cfg)["per"]
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
    assert sajt.region_for("myrorna", "Myrorna, Ropsten")[1] == "Stockholm"
    assert sajt.region_for("bukowskis", "Bukowskis, Hägersten") == ("Hägersten", "Stockholm")
    assert sajt.region_for("bukowskis", "Bukowskis, Göteborg")[1] == "Västsverige och Värmland"
    assert sajt.region_for("bukowskis", "Bukowskis") == ("Stockholm", "Stockholm")
    assert sajt.region_for("bukowskis", "Bukowskis, 126 30 Hägersten")[1] == "Stockholm"
    assert sajt.region_for("bukowskis", "Bukowskis, Bukowskis Malmö")[1] == "Skåne"
    assert sajt.region_for("bukowskis", "Bukowskis, Västberga Allé 3. 126 30 Hägersten -T13")[1] == "Stockholm"
    assert sajt.region_for("auctionet", "Hus, Lundby")[1] == "Övriga Sverige"  # inte "Lund"


def test_bukowskis_lotsida():
    from sources import bukowskis
    ort, beskrivning = bukowskis.tolka_lotsida(_las("bukowskis_lot"))
    assert ort == "Hägersten"
    assert "Björk" in beskrivning and "<" not in beskrivning


def test_prisjamforelse():
    import prisjamforelse as pj
    poster = [
        {"title": "ERIK HÖGLUND, vas, glas.", "state": "sold", "currency": "SEK", "highest_bid": 200, "ends_at": 2_000_000_000},
        {"title": "ERIK HÖGLUND, vaser, 2 st", "state": "sold", "currency": "SEK", "highest_bid": 600, "ends_at": 2_000_000_000},
        {"title": "Erik Höglund vas Boda", "state": "sold", "currency": "SEK", "highest_bid": 400, "ends_at": 2_000_000_000},
        {"title": "ERIK HÖGLUND, skål", "state": "sold", "currency": "SEK", "highest_bid": 9000, "ends_at": 2_000_000_000},  # fel typ
        {"title": "Große Vase im Stil von Erik Höglund", "state": "sold", "currency": "EUR", "highest_bid": 80, "ends_at": 2_000_000_000},
        {"title": "ERIK HÖGLUND, vas", "state": "unsold", "currency": "SEK", "highest_bid": None, "ends_at": 2_000_000_000},
        {"title": "ERIK HÖGLUND, vas", "state": "sold", "currency": "SEK", "highest_bid": 300, "ends_at": 1},  # för gammal
    ]
    priser = pj.tolka(poster, "Erik Höglund vas", gräns=1000)
    assert sorted(priser) == [200, 400, 600]
    res = pj.sammanfatta(priser)
    assert res["median"] == 400 and res["antal"] == 3 and res["lag"] <= 400 <= res["hog"]
    assert pj.sammanfatta([100, 200]) is None


def test_databas_jamforelse(tmp_path):
    db = Databas(tmp_path / "t.db")
    a = auctionet.tolka(AUCTIONET_POST, "Möbler")
    a.jamforsok = "bokhylla teak"
    db.spara(a, 9, "x")
    rader = db.behover_jamforelse(8)
    assert rader[0]["jamforsok"] == "bokhylla teak"
    db.spara_jamforelse(a.nyckel, "bokhylla teak", {"median": 1500, "lag": 1000, "hog": 2000, "antal": 7})
    assert db.behover_jamforelse(8) == []
    t = db.traffar(8)[0]
    assert t["jmf_median"] == 1500 and t["jmf_antal"] == 7


EXPORT = {
    "anvandare": [{"user_id": "u1", "namn": "Per"}],
    "reaktioner": [
        {"user_id": "u1", "nyckel": "a:1", "typ": "gillar", "spar": "hemmet", "titel": "BOKSKÅP, mahogny"},
        {"user_id": "u1", "nyckel": "a:2", "typ": "ogillar", "spar": "hemmet", "titel": "MATTA, persisk"},
        {"user_id": "u1", "nyckel": "a:3", "typ": "kopt", "spar": "samlingen", "titel": "ERIK HÖGLUND, vas"},
    ],
    "anteckningar": [
        {"user_id": "u1", "typ": "gillar", "spar": None, "text": "Bankirlampa i mässing med grön kupa", "sokord": "bankirlampa mässing"},
        {"user_id": "u1", "typ": "har", "spar": "hemmet", "text": "Chesterfield-soffa", "sokord": None},
        {"user_id": "u1", "typ": "gillar", "spar": "samlingen", "text": "Lisa Larson", "sokord": "Lisa Larson"},
    ],
}


def test_smak_profil_och_sokningar():
    import smak
    cfg = {"spar": {
        "hemmet": {"profil": "BAS", "sokningar": {"Möbler": ["bokhylla"]}},
        "samlingen": {"profil": "BAS2", "sokningar": {"Glas": ["Lisa Larson"]}},
    }}
    smak.tillampa(cfg, EXPORT)
    hem, saml = cfg["spar"]["hemmet"], cfg["spar"]["samlingen"]
    assert "BOKSKÅP, mahogny" in hem["profil"] and "MATTA, persisk" in hem["profil"]
    assert "Chesterfield-soffa" in hem["profil"] and "ERIK HÖGLUND" not in hem["profil"]
    assert "Bankirlampa" in hem["profil"] and "Bankirlampa" in saml["profil"]  # utan spår gäller alla
    assert "ERIK HÖGLUND, vas" in saml["profil"]
    assert hem["sokningar"]["Från Min smak"] == ["bankirlampa mässing"]
    assert saml["sokningar"]["Från Min smak"] == ["bankirlampa mässing"]  # Lisa Larson fanns redan
    smak.tillampa(cfg, None)  # ingen data – inget händer


def test_smak_utan_token(monkeypatch):
    import smak
    monkeypatch.delenv("FYNDJAKT_BOT_TOKEN", raising=False)
    assert smak.hamta({"supabase": {"url": "u", "nyckel": "k"}}) is None


def test_sajt_med_konto(tmp_path, monkeypatch):
    import sajt, json, re
    monkeypatch.setattr(sajt, "UT", tmp_path)
    db = Databas(tmp_path / "t.db")
    db.spara(auctionet.tolka(AUCTIONET_POST, "Möbler"), 9, "x")
    html = sajt.bygg(db, {"sajt_min_betyg": 8, "supabase": {"url": "https://x.supabase.co", "nyckel": "sb_publishable_x"}}).read_text(encoding="utf-8")
    data = json.loads(re.search(r"const D = (.*?);\n", html).group(1))
    assert data["supabase"]["url"] == "https://x.supabase.co"
    assert "fyndjakt-kann-igen" in html and 'id="p-smak"' in html


def test_sajt_ar_installerbar(tmp_path, monkeypatch):
    import sajt, json
    monkeypatch.setattr(sajt, "UT", tmp_path)
    html = sajt.bygg(Databas(tmp_path / "t.db"), {"sajt_min_betyg": 8}).read_text(encoding="utf-8")
    assert 'rel="manifest"' in html and 'apple-touch-icon' in html
    m = json.loads((tmp_path / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert m["display"] == "standalone"
    for ikon in m["icons"]:
        assert (tmp_path / ikon["src"]).exists()


def test_raddning_av_avklippt_svar():
    assert bedomning.tolka_svar('{"betyg": 7, "motivering": "Fin men avklip')[0] == 7
    assert bedomning.tolka_svar('```json\n{"betyg": "8", "motivering": "Bra", "jamforsok": "x"}')[:2] == (8, "Bra")
    assert bedomning.tolka_svar("Inget här")[1] == "Kunde inte tolka svaret"


def test_egna_bedomningsregler():
    anrop = {}

    class Falsk:
        class messages:
            @staticmethod
            def create(**kw):
                anrop.update(kw)
                return SimpleNamespace(content=[SimpleNamespace(type="text", text='{"betyg":9,"motivering":"ok"}')])

    a = auctionet.tolka(AUCTIONET_POST)
    bedomning.bedom(a, "STIL", "m", Falsk, "SAMLARREGLER")
    assert "SAMLARREGLER" in anrop["system"] and "MYCKET kräsen" not in anrop["system"]
    bedomning.bedom(a, "STIL", "m", Falsk)
    assert "MYCKET kräsen" in anrop["system"]


# ── Flera användare ────────────────────────────────────────────────
EXPORT2 = {
    "anvandare": [{"user_id": "per-0000-aaaa", "namn": "Per", "admin": True},
                  {"user_id": "kompis-11-bbbb", "namn": "kompis", "admin": False}],
    "profiler": [
        {"id": 5, "user_id": "kompis-11-bbbb", "namn": "Sommarhuset", "beskrivning": "Allmoge och blått",
         "har_redan": "matbord\n- pinnstolar", "max_pris": 3000,
         "sokningar": {"Möbler": ["allmogeskåp", "  allmogeskåp ", "x", "pinnstol " * 20], "Porslin": ["Gustavsberg blå"]}},
        {"id": 6, "user_id": "kompis-11-bbbb", "namn": "Tomt", "sokningar": {}},
        {"id": 7, "user_id": "okand-medlem", "namn": "Ej medlem", "sokningar": {"A": ["b c"]}},
    ],
    "reaktioner": [
        {"user_id": "per-0000-aaaa", "typ": "gillar", "spar": "hemmet", "titel": "PERS BOKSKÅP"},
        {"user_id": "kompis-11-bbbb", "typ": "ogillar", "spar": "p5", "titel": "KOMPISENS MATTA"},
    ],
    "anteckningar": [
        {"user_id": "kompis-11-bbbb", "typ": "gillar", "spar": None, "text": "Blå kakelugn", "sokord": "kakelugn blå"},
        {"user_id": "per-0000-aaaa", "typ": "gillar", "spar": None, "text": "Glob", "sokord": "jordglob"},
    ],
}


def _cfg_med_anvandare():
    import smak
    cfg = {"spar": {"hemmet": {"namn": "Hem", "profil": "BAS", "sokningar": {"Möbler": ["bokhylla"]}}}}
    smak.tillampa(cfg, EXPORT2)
    return cfg


def test_anvandarprofiler_blir_spar():
    cfg = _cfg_med_anvandare()
    assert set(cfg["spar"]) == {"hemmet", "p5"}  # tom profil och icke-medlem hoppas över
    p5 = cfg["spar"]["p5"]
    assert p5["agare"] == "kompis-11-bbbb" and p5["max_pris"] == 3000 and p5["publik"] is False
    assert p5["sokningar"]["Möbler"][0] == "allmogeskåp" and len(p5["sokningar"]["Möbler"]) == 2
    assert all(len(q) <= 60 for qs in p5["sokningar"].values() for q in qs)
    assert "Allmoge och blått" in p5["profil"] and "pinnstolar" in p5["profil"]


def test_larande_haller_isar_anvandare():
    cfg = _cfg_med_anvandare()
    hem, p5 = cfg["spar"]["hemmet"], cfg["spar"]["p5"]
    assert "PERS BOKSKÅP" in hem["profil"] and "KOMPISENS MATTA" not in hem["profil"]
    assert "KOMPISENS MATTA" in p5["profil"] and "PERS BOKSKÅP" not in p5["profil"]
    assert hem["sokningar"]["Från Min smak"] == ["jordglob"]
    assert p5["sokningar"]["Från Min smak"] == ["kakelugn blå"]


def test_samma_annons_hos_flera_anvandare(monkeypatch):
    import main
    from sources import Annons
    anrop = []

    def falsk_sok(q, k, sidor=3):
        anrop.append(q)
        return [Annons("auctionet", "1", "Skåp", "u")]
    for mod in (main.auctionet, main.bukowskis, main.myrorna, main.stadsmissionen):
        monkeypatch.setattr(mod, "sok", falsk_sok)
    cfg = {"kallor": {"auctionet": True, "bukowskis": False, "myrorna": False, "stadsmissionen": False, "tradera": False},
           "spar": {"hemmet": {"namn": "H", "sokningar": {"M": ["skåp"]}},
                    "p5": {"namn": "K", "agare": "kompis-11-bbbb", "sokningar": {"M": ["skåp"]}}}}
    alla = main.hamta_alla(cfg)
    assert sorted(a.nyckel for a in alla) == ["auctionet:1", "kompis-1|auctionet:1"]
    assert {a.spar for a in alla} == {"hemmet", "p5"}


def test_tak_per_anvandare():
    import main
    from sources import Annons
    cfg = {"max_bedomningar_per_korning": 3, "max_bedomningar_per_anvandare": 2,
           "spar": {"h": {}, "p5": {"agare": "k"}}}
    k = [Annons("a", str(i), "t", "u", spar="h") for i in range(5)] + \
        [Annons("a", str(i), "t", "u", spar="p5", prefix="k|") for i in range(5)]
    ut = main.begransa(k, cfg)
    assert sum(a.spar == "h" for a in ut) == 3 and sum(a.spar == "p5" for a in ut) == 2


def test_egna_fynd_syns_inte_publikt(tmp_path, monkeypatch):
    import sajt, json, re
    from dataclasses import replace
    monkeypatch.setattr(sajt, "UT", tmp_path)
    db = Databas(tmp_path / "t.db")
    a = auctionet.tolka(AUCTIONET_POST, "Möbler")
    db.spara(replace(a, spar="hemmet"), 9, "PERSMOTIV")
    db.spara(replace(a, spar="p5", prefix="kompis-1|"), 9, "Kompisens")
    cfg = {"sajt_min_betyg": 8, "spar": {"hemmet": {"namn": "Hem", "sokningar": {"Möbler": []}},
                                         "p5": {"namn": "Sommarhuset", "agare": "kompis-11-bbbb", "sokningar": {"Möbler": []}}}}
    html = sajt.bygg(db, cfg).read_text(encoding="utf-8")
    data = json.loads(re.search(r"const D = (.*?);\n", html).group(1))
    assert data["poster"] == [] and data["spar"] == []  # inget publikt
    assert "Kompisens" not in html and "PERSMOTIV" not in html
    cfg["_admins"] = {"per-0000-aaaa"}
    egna = sajt.anvandarfynd(db, cfg)
    assert sorted(egna) == ["kompis-11-bbbb", "per-0000-aaaa"]
    assert [p["motivering"] for p in egna["per-0000-aaaa"]["poster"]] == ["PERSMOTIV"]
    assert [p["motivering"] for p in egna["kompis-11-bbbb"]["poster"]] == ["Kompisens"]
    assert egna["kompis-11-bbbb"]["spar"][0]["namn"] == "Sommarhuset"


def test_bevakningens_namn_och_sokord_styr_bedomningen():
    import smak
    t = smak.profiltext({"namn": "Tavlor", "beskrivning": "Gröna väggar och mörkt trä.",
                         "sokningar": {"Landskap": ["landskap olja", "Prins Eugen"]}})
    assert "«Tavlor»" in t and "landskap olja" in t and "Gröna väggar" in t
    assert "fel sort" in t


def test_batch_bedomning_med_reserv():
    from types import SimpleNamespace as NS
    class FalskBatches:
        def __init__(s): s.n = 0
        def create(s, requests): s.req = requests; return NS(id="b1", processing_status="in_progress")
        def retrieve(s, bid): s.n += 1; return NS(id=bid, processing_status="ended" if s.n > 1 else "in_progress")
        def results(s, bid):
            yield NS(custom_id="a0", result=NS(type="succeeded", message=NS(content=[NS(type="text", text='{"betyg": 9, "motivering": "Bra", "jamforsok": "x"}')])))
            yield NS(custom_id="a1", result=NS(type="errored"))
            yield NS(custom_id="a2", result=NS(type="succeeded", message=NS(content=[NS(type="text", text="trasigt")])))
    klient = NS(messages=NS(batches=FalskBatches()))
    ut = bedomning.bedom_batch({"a0": {}, "a1": {}, "a2": {}}, klient, intervall=0)
    assert ut == {"a0": (9, "Bra", "x")}  # a1 och a2 bedöms sedan direkt
    a = auctionet.tolka(AUCTIONET_POST)
    f = bedomning.forfragan(a, "PROFIL", "m", None)
    assert f["model"] == "m" and "PROFIL" in f["system"] and f["messages"][0]["content"][-1]["type"] == "text"


def test_webbnotis_kryptering_och_vapid():
    import base64, json, time
    import webbnotis as w
    from cryptography.hazmat.primitives.asymmetric import ec
    ua = ec.generate_private_key(ec.SECP256R1())
    auth = w._b64e(b"0123456789abcdef")
    kropp = w.kryptera(b'{"title":"Hej"}', w._b64e(w._publik_rad(ua)), auth)
    assert w.dekryptera(kropp, ua, auth) == b'{"title":"Hej"}'
    privat = w._b64e(ec.generate_private_key(ec.SECP256R1()).private_numbers().private_value.to_bytes(32, "big"))
    h = w.vapid_huvud("https://web.push.apple.com/abc", privat)
    assert h.startswith("vapid t=") and ", k=B" in h
    data = json.loads(w._b64d(h.split("t=")[1].split(".")[1]))
    assert data["aud"] == "https://web.push.apple.com" and data["exp"] > time.time()


def test_morgonnotis():
    import webbnotis as w, time
    nu = time.time()
    fmt = lambda t: time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t))
    poster = [{"titel": "Gammal", "betyg": 10, "sedd": fmt(nu - 3 * 86400)},
              {"titel": "Ny bra", "betyg": 9, "sedd": fmt(nu - 3600)},
              {"titel": "Ny topp", "betyg": 10, "sedd": fmt(nu - 7200)},
              {"titel": "Ny medel", "betyg": 8, "sedd": fmt(nu - 3600)}]
    n = w.morgonnotis(poster, nu)
    assert n["title"] == "2 nya toppfynd i Fyndjakt" and "Ny topp" in n["body"]
    assert w.morgonnotis(poster[:1], nu) is None


def test_tradera_mot_riktigt_svar():
    import json
    from sources import tradera
    data = json.loads((FIX / "tradera.json").read_text(encoding="utf-8"))
    ann = [tradera.tolka(p, "Porslin") for p in tradera._poster(data)]
    ann = [a for a in ann if a]
    assert ann and all(a.url.startswith("https://www.tradera.com/item/") for a in ann)
    forsta = ann[0]
    assert forsta.pris == 350 and forsta.pris_text == "Köp nu 350 kr"
    assert forsta.bilder[0].startswith("https://img.tradera.net/images/") and "Skick: Gott skick" in forsta.beskrivning
    andra = ann[1]
    assert andra.pris == 99 and andra.pris_text.startswith("Bud 99 kr") and andra.slutar_ts
