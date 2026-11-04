"""Referensbiblioteket: tolkning av Auctionet-poster till referensrader."""
import referens


def post(titel, beskrivning="", skick="", bilder=3, state="sold", bud=(300,), pid=1):
    return {"id": pid, "title": titel, "description": f"<p>{beskrivning}</p>", "condition": f"<p>{skick}</p>", "state": state,
            "ends_at": 1613414940, "house": "RA Auktionsverket Norrköping", "url": "https://auctionet.com/en/1",
            "images": [{"thumb": "t", "w640": f"https://images.auctionet.com/{i}.jpg", "hd": "h"} for i in range(bilder)],
            "bids": [{"amount": b} for b in bud]}


def test_titel_med_formgivare_i_versaler():
    r = referens.tolka_post(post("MARI SIMMULSON. Skålfat, kermik, Upsala-Ekeby.", "Märkt Mari Simmulsson, Upsala-Ekeby 1067, ca 36 x 24 cm."))
    assert r["fabrik"] == "Upsala-Ekeby" and r["formgivare"] == "Mari Simmulson"
    assert r["modell"] == "1067"
    assert r["stampeltext"].startswith("Märkt Mari Simmulsson, Upsala-Ekeby 1067")
    assert r["bild_url"].endswith("/2.jpg") and len(r["bilder"]) == 3   # sista bilden = botten
    assert r["salt"] and r["pris"] == 300 and r["slutade"] == "2021-02-15"
    assert r["url"] == "https://auctionet.com/sv/1" and r["kalla_id"] == "1"


def test_felstavad_formgivare_normaliseras_och_engelsk_text():
    r = referens.tolka_post(post('VASE, "Grafika" Ingrid Atterberg, Upsala-Ekeby.', "Decoration in gray and white. Height about 21 cm. Signed. Model No. 2084."))
    assert r["formgivare"] == "Ingrid Atterberg" and r["modell"] == "2084"
    assert "Signed" in r["stampeltext"] and "Model No. 2084" in r["stampeltext"]
    r2 = referens.tolka_post(post("MARI SIMULSSON. Sculpture, Upsala-Ekeby, earthenware.", "Signed 13/50 mari simmulsson, height 47 cm"))
    assert r2["formgivare"] == "Mari Simmulson"


def test_snedstrecksnummer_och_ue():
    r = referens.tolka_post(post("VAS, keramik, Upsala-Ekeby.", "Stämplad UE 1034/9 A69. Höjd 11 cm."))
    assert r["modell"] == "1034/9" and r["fabrik"] == "Upsala-Ekeby" and r["formgivare"] is None
    r2 = referens.tolka_post(post("VICKE LINDSTRAND. Snäckvas, Upsala-Ekeby.", "märkt Upsala-Ekeby nr 342, signerad VL, höjd 19 cm"))
    assert r2["modell"] == "342" and r2["formgivare"] == "Vicke Lindstrand"


def test_artal_ar_inte_modellnummer():
    r = referens.tolka_post(post("SAXBO. Skål, stengods.", "Stämplad Saxbo, Danmark, nr 1950. Signerad ESN."))
    assert r["fabrik"] == "Saxbo" and r["modell"] is None
    r2 = referens.tolka_post(post("BERNDT FRIBERG. Vas, Gustavsberg Studio 1962.", "Signerad Friberg, studiohand."))
    assert r2["fabrik"] == "Gustavsberg" and r2["formgivare"] == "Berndt Friberg" and r2["modell"] is None


def test_foremalstyp_i_versaler_ar_inte_formgivare():
    r = referens.tolka_post(post("VAS, stengods, Gunnar Nylund, Rörstrand.", "Signerad R GN Sweden."))
    assert r["formgivare"] == "Gunnar Nylund" and r["fabrik"] == "Rörstrand"
    r2 = referens.tolka_post(post("SKÅL, keramik, Gustavsberg.", "Stämplad."))
    assert r2["formgivare"] is None and r2["fabrik"] == "Gustavsberg"


def test_utan_bild_eller_fabrik_ges_upp():
    assert referens.tolka_post(post("MARI SIMMULSON. Skål.", bilder=0)) is None
    assert referens.tolka_post(post("Skål, keramik, okänd.", "Oläslig stämpel.")) is None
    # Sökfrasen räcker inte som fabrik: står den inte i posten är träffen troligen på något annat ord.
    assert referens.tolka_post(post("Skål, keramik.", "Oläslig stämpel."), sokfras="Upsala-Ekeby") is None
    r = referens.tolka_post(post("Skål, keramik, Ekeby.", "Oläslig stämpel."), sokfras="Upsala Ekeby skål")
    assert r and r["fabrik"] == "Upsala-Ekeby" and r["sokfras"] == "Upsala Ekeby skål"


def test_osald_post_markeras():
    r = referens.tolka_post(post("STIG LINDBERG. Fat, Gustavsberg.", "Stämplad.", state="ended", bud=()))
    assert r["salt"] is False and r["pris"] is None


def test_parti_och_objektord_i_versaler():
    r = referens.tolka_post(post("TEA SET, 24 parts, \"Lillemor\", Arthur Percy, Upsala-Ekeby.", "Stämplad."))
    assert r["formgivare"] == "Arthur Percy" and r["parti"] is True
    r2 = referens.tolka_post(post("VASER, 2 st, bl.a Gunnar Nylund, Rörstrand.", "Signerade."))
    assert r2["formgivare"] == "Gunnar Nylund" and r2["parti"] is True
    r3 = referens.tolka_post(post("LISA LARSSON, GUSTAVSBERG: BRAUNBÄR.", ""))
    assert r3["formgivare"] == "Lisa Larson" and r3["parti"] is False
    r4 = referens.tolka_post(post("SAXBO: Egg-shaped stoneware vase.", 'Model no. "1", signed ESN'))
    assert r4["modell"] is None and r4["parti"] is False
    r5 = referens.tolka_post(post("HÄNKELVAS, Ingrid Atterberg, Upsala-Ekeby, 1950-tal och i gott skick.", "Märkt 1034/188."))
    assert r5["parti"] is False and r5["modell"] == "1034/188"
    r6 = referens.tolka_post(post("VAS och SKÅL, Saxbo samt Tobo.", "Stämplade."))
    assert r6["parti"] is True


def test_arsintervall_och_stavningsvarianter():
    r = referens.tolka_post(post("GÖRAN ANDERSSON. Vas, Upsala-Ekeby.", "Modell 1960-67. Stämplad UE."))
    assert r["modell"] is None
    r2 = referens.tolka_post(post("ANNA-LISA THOMPSON. Skål, Upsala-Ekeby.", "Märkt 1081."))
    assert r2["formgivare"] == "Anna-Lisa Thomson" and r2["modell"] == "1081"
    r3 = referens.tolka_post(post("KRUS MED TAPPKRAN, Höganäs.", "Stämplad."))
    assert r3["formgivare"] is None


def test_europeiska_fabriker():
    r = referens.tolka_post(post("VAS, keramik, Strehla, DDR, 1970-tal.", "Stämplad Strehla 1414."))
    assert r["fabrik"] == "Strehla" and r["modell"] == "1414"
    r2 = referens.tolka_post(post("GOLVVAS, West Germany, Scheurich.", "Märkt 517-45 W. Germany."))
    assert r2["fabrik"] == "Scheurich"


def test_nordiska_fabriker_som_saknades():
    for text, fabrik in [("VAS, Syco, Sverige.", "Syco"), ("SKÅL, Tobo.", "Tobo"), ("FAT, Figgjo, Norge.", "Figgjo"),
                         ("VAS, Søholm, Bornholm.", "Søholm"), ("VAS, Michael Andersen & Søn, Bornholm.", "Michael Andersen"),
                         ("VAS, L. Hjorth, Rønne.", "Hjorth"), ("SKÅL, glas, Skrufs glasbruk.", "Skruf"),
                         ("VAS, Gullaskruf.", "Gullaskruf"), ("VAS, Pukeberg.", "Pukeberg")]:
        assert referens.tolka_post(post(text, "Stämplad."))["fabrik"] == fabrik, text
