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


def test_saljplan_tradera_eller_blocket_med_avhamtning():
    assert L("L.saljplan(250).kanal") == "blocket"
    assert L("L.saljplan(399).kanal") == "blocket"
    assert L("L.saljplan(400).kanal") == "tradera"
    assert L("L.saljplan(5000).kanal") == "tradera"            # inga auktionshus längre
    assert L("L.saljplan(0).typ") == "okand"
    assert L("L.saljplan(900, null, {kategori: 'Möbler'}).kanal") == "blocket"
    assert L("L.saljplan(200, null, {kanal: 'tradera'}).kanal") == "tradera"   # ditt eller Claudes val går före
    b = L("L.saljplan(300)")
    assert b["start"] > 300 and b["golv"] < 300 and b["steg"][0] == b["start"] and b["steg"][-1] == b["golv"]   # överpris som sänks
    assert b["nettoSteg"] == b["steg"] and "Blocket" in b["text"] and "Tradera" in b["alternativ"]           # ingen avgift
    t = L("L.saljplan(1000)")
    assert t["start"] < 1000 and t["golv"] <= 500 and t["stegNamn"] == "Utrop" and t["dagar"] == 7
    assert t["netto"] == 1000 - 100 and "hämtar" in t["text"]     # 10 %, inget emballage eller fraktsvinn vid avhämtning


def test_stegens_lage_over_tid():
    # Tradera (800 kr): ett steg i veckan. Upplagd för 15 dagar sedan, steg 0 satt → borde ligga på steg 2 (lägg om).
    nu = 1_800_000_000_000
    upplagd = "new Date(%d - 15 * 86400000).toISOString()" % nu
    plan = L(f"L.saljplan(800, {{upplagd: {upplagd}, steg_satt: 0, nu: {nu}}})")
    lage = plan["lage"]
    assert lage["dagar"] == 15 and lage["satt"] == 0 and lage["bor"] == 2 and lage["sank"] == plan["steg"][2]
    # Samma dag som upplagd: inget att sänka, nästa steg om 7 dagar.
    lage = L(f"L.saljplan(800, {{upplagd: new Date({nu}).toISOString(), steg_satt: 0, nu: {nu}}}).lage")
    assert lage["sank"] is None and lage["nasta"] == 7


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
    # Vi säljer på Tradera och Blocket med avhämtning: Blocket utan avgift, Tradera 10 % (högst 200 kr), ingen frakt.
    rader = L("L.bestChannel(1000, 200)")
    assert [r["kanal"] for r in rader] == ["blocket", "tradera"]
    assert rader[0]["netto"] == 1000 and rader[1]["netto"] == 900 and rader[1]["vinst"] == 700
    assert all(a["vinst"] >= b["vinst"] for a, b in zip(rader, rader[1:]))
    # Dyrt föremål: Traderas tak på 200 kr. Auktionshusen går fortfarande att jämföra om man ber om dem.
    assert L("L.bestChannel(10000, 0)")[1]["netto"] == 9800
    assert {r["kanal"] for r in L("L.bestChannel(10000, 0, ['bukowskis', 'tradera'])")} == {"bukowskis", "tradera"}


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
    assert L("L.varde({uppskattat_min: 100, uppskattat_max: 300})") is None   # gamla uppskattningar räknas inte längre
    assert L("L.varde({marknad_min: 100})") == 100
    assert L("L.varde({marknad_min: 300, marknad_max: 500, uppskattat_min: 2000, uppskattat_max: 9000})") == 400
    assert L("L.varde({})") is None
    s = L("L.sammanstallning([{lada:'salt', inkopspris: 100, salt_for: 400}, {lada:'salt', inkopspris: 50, salt_for: 100}, {lada:'egen', auk_median: 900}])")
    assert s["salt"] == {"antal": 2, "varde": 0, "inkopt": 150, "salt": 500, "vinst": 350}
    assert s["egen"]["varde"] == 900


def test_flipp_rakning_samma_som_python():
    """Förklaringen på fyndkortet räknar exakt som flipp.kop_max."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import flipp
    for median in (600, 1000, 2582, 4000):
        for kalla in ("tradera", "auctionet", "bukowskis", "myrorna"):
            assert L(f"L.flippRakning({median}, '{kalla}').kopMax") == flipp.kop_max(median, kalla), (median, kalla)
    r = L("L.flippRakning(2582, 'tradera')")
    assert r == {"slutpris": 2582, "provision": 200, "netto": 2382, "tak": 1191, "halva": True, "frakt": 80, "prov": 0, "efterFrakt": 1111, "kopMax": 1111}
    assert L("L.flippRakning(300, 'myrorna').kopMax") is None   # lönar sig aldrig


def test_saljplan_sager_var_den_ska_ligga():
    p = L("L.saljplan(1500)")
    assert p["kanal"] == "tradera" and "Tradera" in p["kanalNamn"] and p["varfor"] and "Blocket" in p["alternativ"]
    assert all(abs(n - L(f"L.nettoHamtning('tradera', {x})")) <= 0.5 for n, x in zip(p["nettoSteg"], p["steg"]))


# ── Till salu: Att fixa → Klar → Upplagd ───────────────────────────────
def test_salj_klar_checklista():
    tom = L('L.saljKlar({tradera_pris: 400, bilder: [{}]})')
    assert tom["steg"] == "fixa" and not tom["alla"]
    assert [k["id"] for k in tom["saknas"]] == ["bilder", "annons", "matt"]
    text = "Vas ur serien Berså, formgiven av Stig Lindberg för Gustavsberg. Mått: [mått]. Inga skador."
    halv = L(f'L.saljKlar({{tradera_pris: 400, bilder: [{{}},{{}},{{}}], annons_rubrik: "Berså vas", annons_text: {json.dumps(text)}}})')
    assert [k["id"] for k in halv["saknas"]] == ["matt"]
    full = L(f'L.saljKlar({{tradera_pris: 400, bilder: [{{}},{{}},{{}}], annons_rubrik: "Berså vas", annons_text: L.sattMatt({json.dumps(text)}, "höjd 21 cm")}})')
    assert full["alla"] and full["steg"] == "fixa"
    assert L('L.saljKlar({klar: "2026-10-31"}).steg') == "klar"
    assert L('L.saljKlar({klar: "2026-10-31", upplagd: "2026-11-01"}).steg') == "upplagd"


def test_satt_matt():
    assert L('L.sattMatt("Vas.\\nMått: [mått]\\nFint skick.", "höjd 21 cm")') == "Vas.\nMått: höjd 21 cm\nFint skick."
    assert L('L.sattMatt("Vas.", "höjd 21 cm")') == "Vas.\nMått: höjd 21 cm."
    assert L('L.sattMatt("", "höjd 21 cm")') == "Mått: höjd 21 cm."


# ── Sälj: kvällens lista och pengarna ───────────────────────────────────

def test_salj_uppgifter_narmast_pengarna_forst():
    nu = 1_762_000_000_000  # ms
    text = json.dumps("Vas. Mått: höjd 21 cm. Hämtas i Stockholm – skickas inte.")
    dag = lambda n: f"new Date({nu} - {n} * 86400000).toISOString()"
    lista = (
        "[{id:'a', lada:'salj', namn:'A', tradera_pris: 800},"                                                  # saknar bilder → fota
        f" {{id:'b', lada:'salj', namn:'B', tradera_pris: 600, bilder:[{{}},{{}},{{}}], annons_rubrik:'x', annons_text:{text}, klar: 'x'}},"  # klar → lägg upp
        f" {{id:'c', lada:'salj', namn:'C', tradera_pris: 500, kanal:'blocket', upplagd: {dag(9)}, steg_satt: 0}},"  # dag 9 på Blocket → sänk (645 → 595)
        f" {{id:'d', lada:'salj', namn:'D', tradera_pris: 500, kanal:'tradera', upplagd: {dag(8)}, steg_satt: 0}},"  # auktion slut → resultat (nytt utrop 395 × 0,85 → 345)
        f" {{id:'e', lada:'salj', namn:'E', tradera_pris: 500, kanal:'blocket', upplagd: {dag(2)}, steg_satt: 0}},"  # ligger ute
        " {id:'f', lada:'egen', namn:'F', tradera_pris: 9000}]"                                                 # inte till salu
    )
    u = L(f"L.saljUppgifter({lista}, {nu}).map(u => [u.it.id, u.typ, u.pris ?? null])")
    assert u == [["d", "resultat", 345], ["c", "sank", 595], ["b", "laggupp", None], ["a", "fota", None], ["e", "ute", None]]
    k = L(f"L.kvallensLista(L.saljUppgifter({lista}, {nu}), 30)")
    assert [x["it"]["id"] for x in k["lista"]] == ["d", "c", "b", "a"] and k["minuter"] == 13 and k["kvar"] == 0
    kort = L(f"L.kvallensLista(L.saljUppgifter({lista}, {nu}), 3)")
    assert [x["it"]["id"] for x in kort["lista"]] == ["d", "c"] and kort["kvar"] == 2


def test_salj_pengar_manad_och_ar():
    nu = "new Date('2026-11-03T10:00:00Z').getTime()"
    lista = ("[{lada:'salt', salt_for: 1000, salt_kanal:'tradera', salt_datum:'2026-11-02', inkopspris: 200},"
             " {lada:'salt', salt_for: 500, salt_kanal:'blocket', salt_datum:'2026-10-20', inkopspris: 100},"
             " {lada:'salt', salt_for: 300, salt_kanal:'tradera', salt_datum:'2025-12-24', inkopspris: 50},"
             " {lada:'salj', tradera_pris: 400, kanal:'blocket', upplagd: '2026-11-01T00:00:00Z', steg_satt: 0},"
             " {lada:'salj', tradera_pris: 250}]")
    p = L(f"L.saljPengar({lista}, {nu})")
    assert p["manad"] == {"antal": 1, "salt": 1000, "inkop": 200, "avgift": 100, "vinst": 700}
    assert p["ar"]["antal"] == 2 and p["ar"]["salt"] == 1500 and p["ar"]["vinst"] == 1500 - 300 - 100
    assert p["ute"]["antal"] == 1 and p["ute"]["begart"] == 495   # Blocket: 400 × 1,25 avrundat
    assert p["vantar"] == {"antal": 1, "varde": 250}


def test_forvantat_galler_hela_partiet():
    assert L("L.forvantat({tradera_pris: 450, antal: 3})") == 450                       # satt utgångspris – för annonsen
    assert L("L.forvantat({auk_median: 600, antal: 3})") == 600                         # omvärderingen lagrar partiets värde
    assert L("L.forvantat({marknad_min: 300, marknad_max: 700, antal: 3})") == 500      # Claudes uppskattning gäller alla
    assert L("L.forvantat({marknad_min: 300, marknad_max: 700})") == 500
    assert L("L.forvantat({})") is None


def test_satt_matt_ersatter_aven_claudes_platshallare():
    assert L('L.sattMatt("Mått [ej angivna]: ett större och två mindre fat.", "längd 38 och 34 cm")') == "Mått längd 38 och 34 cm: ett större och två mindre fat."
