"""Prov inför referensbiblioteket för stämplar: hur många sålda poster på Auctionet har stämpeltext i katalogen
och bottenfoto, och finns bilderna för gamla poster kvar? Skriver sammanfattningen till data/probe/referensprov.json
och till loggen. Körs av GitHub Actions (miljön där sajten byggs når inte Auctionet).

Kör:  python tools/referensprov.py
"""
import collections
import json
import pathlib
import re
import sys
import time
from datetime import datetime, timezone

import requests

API = "https://auctionet.com/api/v2/items.json"
H = {"User-Agent": "Fyndjakt/1.0 (privat samling; referensprov)"}
UT = pathlib.Path(__file__).parent.parent / "data" / "probe"
UT.mkdir(parents=True, exist_ok=True)

FABRIKER = ["Upsala-Ekeby", "Upsala Ekeby Atterberg", "Upsala Ekeby Simmulson", "Gustavsberg Stig Lindberg", "Gustavsberg Lisa Larson",
            "Gustavsberg Friberg", "Rörstrand Nylund", "Rörstrand Hertha Bengtson", "Rörstrand Stålhane", "Arabia Finland",
            "Boda Höglund", "Kosta Vicke Lindstrand", "Orrefors", "Saxbo", "Palshus", "Bo Fajans", "Gefle Percy", "Höganäs keramik",
            "Laholm keramik", "Royal Copenhagen", "Tilgmans", "Nittsjö", "Jie Gantofta"]
SIDOR = 6
STAMPEL = re.compile(r"(stämpl\w*|sign\w*|märkt|märkning|monogram|etikett|präglad|ristad|numrerad|modellnummer|dekornummer)[^.;]{0,90}", re.I)
MODELL = re.compile(r"\b\d{3,4}(?:/\d{1,3})?\b")


def ren(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def hamta(fras: str):
    poster = []
    for sida in range(1, SIDOR + 1):
        try:
            r = requests.get(API, params={"q": fras, "is": "ended", "per_page": 48, "page": sida}, headers=H, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"  {fras} sida {sida}: {e}")
            break
        d = r.json()
        poster += d.get("items", [])
        if sida >= (d.get("pagination") or {}).get("total_pages", 1):
            break
        time.sleep(1)
    return poster


def main():
    alla = {}
    for fras in FABRIKER:
        for p in hamta(fras):
            alla.setdefault(p.get("id"), (fras, p))
        print(f"{fras}: {len(alla)} unika poster hittills")
        time.sleep(1)
    print("Fältnamn i en post:", sorted(next(iter(alla.values()))[1].keys()) if alla else "-")

    nu = datetime.now(timezone.utc).timestamp()
    stat = collections.Counter()
    per_ar = collections.defaultdict(collections.Counter)
    exempel, modeller = [], collections.Counter()
    for fras, p in alla.values():
        sald = p.get("state") == "sold"
        text = ren(p.get("description", "")) + " " + ren(p.get("condition", ""))
        bilder = p.get("images") or []
        m = STAMPEL.search(text)
        ar = datetime.fromtimestamp(p.get("ends_at") or nu, timezone.utc).year
        stat["poster"] += 1
        per_ar[ar]["poster"] += 1
        if sald:
            stat["salda"] += 1; per_ar[ar]["salda"] += 1
        if m:
            stat["med_stampeltext"] += 1; per_ar[ar]["med_stampeltext"] += 1
        if len(bilder) >= 2:
            stat["minst_2_bilder"] += 1
        if m and len(bilder) >= 2:
            stat["stampeltext_och_2_bilder"] += 1; per_ar[ar]["stampeltext_och_2_bilder"] += 1
            if sald:
                stat["salda_stampeltext_2_bilder"] += 1
            if len(exempel) < 40:
                exempel.append({"fras": fras, "titel": (p.get("title") or "")[:90], "stampel": m.group(0)[:120], "bilder": len(bilder),
                                "ar": ar, "pris": p.get("highest_bid"), "url": p.get("url")})
            for mod in MODELL.findall(m.group(0)):
                modeller[(fras.split()[0], mod)] += 1

    # Finns bilderna kvar för gamla poster? HEAD på första och sista bilden för ett urval per år.
    bildkoll = collections.defaultdict(collections.Counter)
    urval = collections.defaultdict(list)
    for fras, p in alla.values():
        ar = datetime.fromtimestamp(p.get("ends_at") or nu, timezone.utc).year
        if (p.get("images") or []) and len(urval[ar]) < 6:
            urval[ar].append(p)
    for ar, lista in sorted(urval.items()):
        for p in lista:
            bilder = p["images"]
            for vilken, b in (("forsta", bilder[0]), ("sista", bilder[-1])):
                url = b.get("w640") or b.get("hd") or next(iter(b.values()), None)
                try:
                    r = requests.head(url, headers=H, timeout=20, allow_redirects=True)
                    bildkoll[ar][f"{vilken}_{r.status_code}"] += 1
                except Exception:
                    bildkoll[ar][f"{vilken}_fel"] += 1
            time.sleep(0.3)

    ut = {"stat": dict(stat), "per_ar": {str(k): dict(v) for k, v in sorted(per_ar.items())},
          "bildkoll_per_ar": {str(k): dict(v) for k, v in sorted(bildkoll.items())},
          "vanligaste_modeller": [{"fabrik": f, "modell": m, "antal": n} for (f, m), n in modeller.most_common(40)],
          "exempel": exempel, "bildfalt": sorted((next(iter(alla.values()))[1].get("images") or [{}])[0].keys()) if alla else []}
    (UT / "referensprov.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(ut, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
