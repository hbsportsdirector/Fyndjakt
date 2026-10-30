"""Tester för sajtens delade logik (site/logik.js): prisstege, kanaler, köptak och "slutar snart".
Körs med node – finns inte node hoppas testerna över."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

LOGIK = Path(__file__).parent.parent / "site" / "logik.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node saknas")


def L(uttryck: str):
    """Kör ett JavaScript-uttryck mot Logik och returnerar resultatet som Python-data."""
    kod = f"const L = require({json.dumps(str(LOGIK))}); process.stdout.write(JSON.stringify({uttryck}) ?? 'null');"
    r = subprocess.run(["node", "-e", kod], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


# ── Prisstege och säljplan ─────────────────────────────────────────────

def test_prisstege_start_sank_och_golv():
    # 800 kr: start +15 % → 920 → avrundat 895, −10 % per steg, golv 85 % → 680 → 695.
    s = L("L.prisstege(800)")
    assert s["start"] == 895 and s["golv"] == 695
    assert s["steg"][0] == s["start"] and s["steg"][-1] == s["golv"]
    assert all(a > b for a, b in zip(s["steg"], s["steg"][1:]))  # strikt fallande
    assert all(v % 5 == 0 for v in s["steg"])                     # "snygga" priser (x95, x45)


def test_prisstege_aldrig_under_golvet():
    for e in (300, 500, 1234, 2000):
        s = L(f"L.prisstege({e})")
        # Priserna avrundas till "snygga" tal (x45/x95 under 1 000 kr, x95 över) – högst ett halvt steg från 85 % och 115 %.
        assert min(s["steg"]) == s["golv"] and abs(s["golv"] - e * 0.85) <= (30 if e < 1000 else 55)
        assert abs(s["start"] - e * 1.15) <= (30 if e < 1000 else 55)


def test_saljplan_per_prisklass():
    assert L("L.saljplan(250).typ") == "auktion"
    assert L("L.saljplan(299).typ") == "auktion"
    assert L("L.saljplan(300).typ") == "stege"
    assert L("L.saljplan(2000).typ") == "stege"
    assert L("L.saljplan(2001).typ") == "auktionshus"
    assert L("L.saljplan(0).typ") == "okand"
    assert "1 kr" in L("L.saljplan(100).text")
    assert L("L.saljplan(5000).netto") == int(5000 - (5000 * 0.175 + 170 + 5000 * 0.0195) - 15 - 100 + 0.5)  # 3 742,5 → 3 743


def test_stegens_lage_over_tid():
    # Upplagd för 25 dagar sedan, steg 0 satt → borde ligga på steg 2 (sänk).
    nu = 1_800_000_000_000
    upplagd = "new Date(%d - 25 * 86400000).toISOString()" % nu
    lage = L(f"L.saljplan(800, {{upplagd: {upplagd}, steg_satt: 0, nu: {nu}}}).lage")
    assert lage["dagar"] == 25 and lage["satt"] == 0 and lage["bor"] == 2
    assert lage["sank"] == 695
    # Samma dag som upplagd: inget att sänka, nästa sänkning om 10 dagar.
    lage = L(f"L.saljplan(800, {{upplagd: new Date({nu}).toISOString(), steg_satt: 0, nu: {nu}}}).lage")
    assert lage["sank"] is None and lage["nasta"] == 10


# ── Kanaler ────────────────────────────────────────────────────────────

def test_channel_net_avgifter():
    # Tradera 10 % (max 200 kr), emballage 15 kr, svinn 2 %.
    assert L("L.avgift('tradera', 1000)") == 100
    assert L("L.avgift('tradera', 5000)") == 200
    assert L("L.avgift('blocket', 1000)") == 0
    assert L("L.avgift('bukowskis', 1000)") == pytest.approx(175 + 170 + 19.5)
    assert L("L.avgift('auktionsverket', 1000)") == pytest.approx(170 + 170 + 17.5)
    assert L("L.avgift('catawiki', 1000)") == pytest.approx(135)
    assert L("L.channelNet('tradera', 1000)") == pytest.approx(1000 - 100 - 15 - 20)
    assert L("L.channelNet('blocket', 1000)") == pytest.approx(1000 - 15 - 20)


def test_best_channel_sorterar_pa_vinst():
    rader = L("L.bestChannel(1000, 200)")
    assert [r["kanal"] for r in rader][:1] == ["tradera"]            # billigast under 2 000 kr
    assert rader[0]["vinst"] == 665 and rader[0]["netto"] == 865
    assert all(a["vinst"] >= b["vinst"] for a, b in zip(rader, rader[1:]))
    assert "blocket" not in [r["kanal"] for r in rader]              # jämförs inte som standard
    # Dyrt föremål: Traderas tak på 200 kr gör den fortfarande billigast, men auktionshusen är med i listan.
    dyra = L("L.bestChannel(10000, 0)")
    assert {r["kanal"] for r in dyra} == {"tradera", "bukowskis", "auktionsverket", "catawiki"}


# ── Köptak och besked i butiken ────────────────────────────────────────

def test_koptak_flipp_mot_samling():
    assert L("L.koptak(900, false)") == {"tak": 297, "faktor": 0.33, "regel": "flipp: en tredjedel av typiskt slutpris"}
    assert L("L.koptak(900, true)") == {"tak": 540, "faktor": 0.6, "regel": "samling: 60 % av typiskt slutpris"}
    assert L("L.koptak(null, true).tak") is None


def test_butikbesked():
    b = L("L.butikBesked({median: 900, sakerhet: 0.8}, 250, false)")
    assert b["besked"] == "KÖP" and b["tak"] == 297 and "flipp" in b["skal"]
    b = L("L.butikBesked({median: 900, sakerhet: 0.8}, 400, false)")
    assert b["besked"] == "KÖP INTE" and "297 kr" in b["skal"]
    # Passar smaken: 60 % → 540 kr är OK.
    assert L("L.butikBesked({median: 900, sakerhet: 0.8, passar_smak: true}, 400, false).besked") == "KÖP"
    # Osäker utan stämpelbild → fota stämpeln först; med stämpelbild får man ett besked.
    assert L("L.butikBesked({median: 900, sakerhet: 0.3}, 100, false).besked") == "FOTA STÄMPELN FÖRST"
    assert L("L.butikBesked({median: 900, sakerhet: 0.3}, 100, true).besked") == "KÖP"
    # Nyproduktion → köp inte, oavsett pris.
    b = L("L.butikBesked({median: 900, sakerhet: 0.9, nyproduktion: true, varning: 'krönt R'}, 10, true)")
    assert b["besked"] == "KÖP INTE" and "Nyproduktion" in b["skal"] and "krönt R" in b["skal"]
    # Utan pris: säg vad det får kosta. Medianen räknas ur min–max när den saknas.
    b = L("L.butikBesked({marknad_min: 800, marknad_max: 1000, sakerhet: 0.9}, null, false)")
    assert b["median"] == 900 and b["besked"] == "KÖP UNDER 297 kr"


# ── Fynd: slutar snart ─────────────────────────────────────────────────

NU = 1_800_000_000


def test_slutar_snart_urval_och_ordning():
    poster = [
        {"nyckel": "a", "slutar_ts": NU + 3600 * 20, "betyg": 7},        # inom 24 h
        {"nyckel": "b", "slutar_ts": NU + 3600 * 2, "betyg": 5},         # inom 24 h, slutar först
        {"nyckel": "c", "slutar_ts": NU + 3600 * 30, "betyg": 10},       # för långt bort
        {"nyckel": "d", "slutar_ts": NU - 10, "betyg": 10},              # avslutad
        {"nyckel": "e", "betyg": 10},                                    # köp nu – ingen sluttid
    ]
    assert [p["nyckel"] for p in L(f"L.slutarSnart({json.dumps(poster)}, {NU})")] == ["b", "a"]


def test_bradskande_banner():
    poster = [
        {"nyckel": "a", "slutar_ts": NU + 3600 * 5, "betyg": 8},                     # ≤ 6 h och betyg 8
        {"nyckel": "b", "slutar_ts": NU + 3600 * 5, "betyg": 4, "pris": 100, "jmf_median": 300},  # kvot 0,33
        {"nyckel": "c", "slutar_ts": NU + 3600 * 5, "betyg": 4, "pris": 200, "jmf_median": 300},  # kvot 0,67 – nej
        {"nyckel": "d", "slutar_ts": NU + 3600 * 7, "betyg": 10},                    # mer än 6 h kvar
        {"nyckel": "e", "slutar_ts": NU + 60, "betyg": 2},                           # lågt betyg, ingen kvot
    ]
    assert [p["nyckel"] for p in L(f"L.bradskande({json.dumps(poster)}, {NU})")] == ["a", "b"]
    assert L(f"L.bradskande([], {NU})") == []
    assert L("L.tidText(90)") == "1 min" and L("L.tidText(3600 * 5 + 120)") == "5 h 2 min" and L("L.tidText(86400 * 2)") == "2 d 0 h"
    assert L("L.tidText(-5)") == "avslutad"


def test_samlingens_varde():
    it = {"auk_median": 500, "uppskattat_min": 100, "uppskattat_max": 300, "antal": 2}
    assert L(f"L.varde({json.dumps(it)})") == 500           # auktionsmedianen först – den gäller hela posten
    assert L("L.varde({uppskattat_min: 100, uppskattat_max: 300})") == 200
    assert L("L.varde({marknad_min: 100})") == 100
    assert L("L.varde({marknad_min: 300, marknad_max: 500, uppskattat_min: 2000, uppskattat_max: 9000})") == 400  # uppskattning före egen
    assert L("L.varde({})") is None
    s = L("L.sammanstallning([{lada:'salt', inkopspris: 100, salt_for: 400}, {lada:'salt', inkopspris: 50, salt_for: 100}, {lada:'egen', auk_median: 900}])")
    assert s["salt"] == {"antal": 2, "varde": 0, "inkopt": 150, "salt": 500, "vinst": 350}
    assert s["egen"]["varde"] == 900
