"""Fyller referensbiblioteket: hämtar avslutade auktioner på Auctionet för sökfraserna i tools/referens_fraser.txt,
tolkar dem (referens.py) och sparar i Supabase-tabellen referens med bot-nyckeln.

Gjord för att köras hemma (Windows eller Linux) och kunna avbrytas och startas om: läget per fras sparas i
data/referens_lage.json (ligger inte i git), och redan hämtade sidor hoppas över. En sekund mellan anropen –
Auctionet ska inte märka av oss. Se docs/referens_hemma.md.

Kör:  python tools/referens_hamta.py            (alla fraser i tools/referens_fraser.txt)
      python tools/referens_hamta.py "Saxbo"    (bara den frasen)
      python tools/referens_hamta.py --max-sidor 20   (högst 20 sidor à 48 per fras – bra för ett första varv)
Miljö: FYNDJAKT_BOT_TOKEN (samma nyckel som nattkörningen). URL och publik nyckel läses ur config.yaml.
Behöver bara paketet requests (python -m pip install requests).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import re

import requests

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT))
import referens  # noqa: E402

API = "https://auctionet.com/api/v2/items.json"
H = {"User-Agent": "Fyndjakt/1.0 (privat samling; referensbibliotek)"}
FRASER = ROT / "tools" / "referens_fraser.txt"
LAGE = ROT / "data" / "referens_lage.json"
PER_SIDA = 48
BATCH = 200
PAUS = 1.0


def las_fraser() -> list[str]:
    return [r.strip() for r in FRASER.read_text(encoding="utf-8").splitlines() if r.strip() and not r.startswith("#")]


def las_lage() -> dict:
    try:
        return json.loads(LAGE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def spara_lage(lage: dict) -> None:
    LAGE.parent.mkdir(parents=True, exist_ok=True)
    LAGE.write_text(json.dumps(lage, ensure_ascii=False, indent=1), encoding="utf-8")


def las_supabase() -> tuple[str | None, str | None]:
    """supabase.url och supabase.nyckel ur config.yaml – utan yaml-paketet, som saknar färdigt bygge för nya Python-versioner."""
    text = (ROT / "config.yaml").read_text(encoding="utf-8")
    block = re.search(r"^supabase:\n((?:[ \t]+.*\n?)+)", text, re.M)
    hitta = lambda namn: (re.search(rf"^\s+{namn}:\s*(\S+)", block.group(1), re.M) if block else None)
    return (hitta("url").group(1) if hitta("url") else None), (hitta("nyckel").group(1) if hitta("nyckel") else None)


class Databas:
    def __init__(self):
        self.url, self.nyckel = las_supabase()
        self.token = os.environ.get("FYNDJAKT_BOT_TOKEN", "").strip()
        if not (self.url and self.nyckel and self.token):
            sys.exit("Saknar FYNDJAKT_BOT_TOKEN (miljövariabel) eller supabase.url/nyckel i config.yaml.")

    def spara(self, rader: list[dict]) -> int:
        if not rader:
            return 0
        for forsok in range(4):
            try:
                r = requests.post(f"{self.url}/rest/v1/rpc/referens_spara", json={"token": self.token, "poster": rader},
                                  headers={"apikey": self.nyckel, "Authorization": f"Bearer {self.nyckel}", "Content-Type": "application/json"}, timeout=120)
                if r.status_code == 200:
                    return int(r.json())
                if r.status_code in (401, 403, 400) and "nyckel" in r.text:
                    sys.exit("Supabase svarade 'ogiltig nyckel' – kontrollera FYNDJAKT_BOT_TOKEN.")
                print(f"  Supabase {r.status_code}: {r.text[:200]}")
            except requests.RequestException as e:
                print(f"  Supabase: {e}")
            time.sleep(5 * (forsok + 1))
        raise SystemExit("Kunde inte spara till Supabase – avbryter (läget är sparat, kör igen senare).")

    def kolla_nyckel(self) -> None:
        """Stoppar direkt om nyckeln inte stämmer – i stället för efter första sidan."""
        r = requests.post(f"{self.url}/rest/v1/rpc/fyndjakt_kolla_nyckel", json={"token": self.token},
                          headers={"apikey": self.nyckel, "Authorization": f"Bearer {self.nyckel}", "Content-Type": "application/json"}, timeout=60)
        if r.status_code != 200 or "nyckel" in r.text:
            sys.exit("Supabase svarade 'ogiltig nyckel' – FYNDJAKT_BOT_TOKEN stämmer inte med någon hash i databasen.\n"
                     "Hashen av din nyckel:  python -c \"import hashlib,os;print(hashlib.sha256(os.environ['FYNDJAKT_BOT_TOKEN'].strip().encode()).hexdigest())\"")
        print("Nyckeln stämmer.")

    def antal(self) -> list[dict]:
        r = requests.post(f"{self.url}/rest/v1/rpc/referens_antal", json={},
                          headers={"apikey": self.nyckel, "Authorization": f"Bearer {self.nyckel}", "Content-Type": "application/json"}, timeout=60)
        return r.json() if r.status_code == 200 else []


def hamta_sida(fras: str, sida: int) -> tuple[list[dict], int]:
    """Returnerar (poster, total_pages). Tom lista + 0 när Auctionet säger stopp (302 efter ~10 000 träffar)."""
    for forsok in range(4):
        try:
            r = requests.get(API, params={"q": fras, "is": "ended", "per_page": PER_SIDA, "page": sida}, headers=H, timeout=30, allow_redirects=False)
            if r.status_code in (301, 302, 404):
                return [], 0
            r.raise_for_status()
            d = r.json()
            return d.get("items", []), int((d.get("pagination") or {}).get("total_pages") or 1)
        except (requests.RequestException, ValueError) as e:
            print(f"  {fras} sida {sida}: {e} – väntar")
            time.sleep(10 * (forsok + 1))
    return [], 0


def kor(fraser: list[str], max_sidor: int, db: Databas, sedda: set[str]) -> None:
    lage = las_lage()
    for fras in fraser:
        f = lage.setdefault(fras, {"sida": 0, "klar": False, "sparade": 0})
        if f["klar"]:
            print(f"{fras}: klar sedan tidigare ({f['sparade']} sparade) – hoppar över")
            continue
        sida, batch = f["sida"] + 1, []
        print(f"{fras}: börjar på sida {sida}")
        while sida <= max_sidor:
            poster, total = hamta_sida(fras, sida)
            if not poster:
                f["klar"] = True
                break
            for p in poster:
                pid = str(p.get("id"))
                if pid in sedda:
                    continue
                rad = referens.tolka_post(p, fras)
                if rad:
                    batch.append(rad)
                    sedda.add(pid)
            if len(batch) >= BATCH:
                f["sparade"] += db.spara(batch); batch = []
            f["sida"] = sida
            if sida % 10 == 0:
                print(f"  sida {sida}/{min(total, max_sidor)} – {f['sparade'] + len(batch)} sparade")
                spara_lage(lage)
            if sida >= total:
                f["klar"] = True
                break
            sida += 1
            time.sleep(PAUS)
        f["sparade"] += db.spara(batch)
        spara_lage(lage)
        print(f"{fras}: {'klar' if f['klar'] else 'pausad vid sida ' + str(f['sida'])} – {f['sparade']} sparade")
        time.sleep(PAUS)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fyller referensbiblioteket från Auctionet.")
    ap.add_argument("fraser", nargs="*", help="sökfraser (annars alla i tools/referens_fraser.txt)")
    ap.add_argument("--max-sidor", type=int, default=250, help="högst så många sidor à 48 per fras (standard 250)")
    ap.add_argument("--om", action="store_true", help="börja om från sida 1 för fraserna (sparade rader uppdateras)")
    ap.add_argument("--status", action="store_true", help="visa bara hur många referenser som finns per fabrik")
    a = ap.parse_args()
    db = Databas()
    db.kolla_nyckel()
    if a.status:
        for r in db.antal():
            print(f"{r['fabrik']:<20} {r['antal']:>6} varav sålda {r['salda']:>6}, med modellnummer {r['med_modell']:>6}")
        return
    fraser = a.fraser or las_fraser()
    if a.om:
        lage = las_lage()
        for fr in fraser:
            lage.pop(fr, None)
        spara_lage(lage)
    sedda: set[str] = set()   # dubbletter inom körningen – mellan körningar sköter databasen det (upsert)
    try:
        kor(fraser, a.max_sidor, db, sedda)
    except KeyboardInterrupt:
        print("\nAvbrutet – läget är sparat, kör igen för att fortsätta.")
    print("Nu finns:")
    for r in db.antal():
        print(f"  {r['fabrik']:<20} {r['antal']:>6} (sålda {r['salda']}, med modellnummer {r['med_modell']})")


if __name__ == "__main__":
    main()
