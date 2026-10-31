"""Dubbelkoll av ett värde: listar avslutade auktioner på Auctionet (sålda och osålda) för en eller flera sökfraser,
med antal delar och pris per del – så att man kan jämföra parti mot parti i stället för att lita på en median.

Sökfraserna står en per rad i tools/dubbelkoll.txt (rader som börjar med # hoppas över). Körs av GitHub Actions
när filen ändras (miljön där sajten byggs når inte Auctionet). Läs resultatet i körningens logg.

Kör:  python tools/dubbelkoll.py ["sökfras" …]
"""
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import prisjamforelse  # noqa: E402

FIL = Path(__file__).with_suffix(".txt")
SIDOR = 6
DELAR = re.compile(r"\b(\d{1,3})\s*(?:delar|dlr|st\b|stycken|pcs)", re.I)


def delar(titel: str, beskrivning: str) -> int:
    """Antal delar: ur titeln (prisjamforelse.styck_i), annars ur beskrivningen ("ca 74 delar")."""
    n = prisjamforelse.styck_i(titel)
    if n > 1:
        return n
    m = DELAR.search(beskrivning or "")
    return int(m.group(1)) if m else 1


def hamta(fras: str) -> list[dict]:
    ut = []
    for sida in range(1, SIDOR + 1):
        r = requests.get(prisjamforelse.API, params={"q": fras, "is": "ended", "per_page": 48, "page": sida},
                         headers=prisjamforelse.HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        for p in data.get("items", []):
            beskr = re.sub(r"<[^>]+>", " ", p.get("description") or "")
            # Orden får stå i titeln eller beskrivningen – modellnummer ("1034") står sällan i titeln.
            if p.get("currency") != "SEK" or not prisjamforelse.relevant(((p.get("title") or "") + " " + beskr).lower(), fras):
                continue
            sald = p.get("state") == "sold"
            pris = (p.get("highest_bid") or max((b.get("amount", 0) for b in p.get("bids") or []), default=0)) if sald else 0
            titel = (p.get("title") or "").strip()
            ut.append({"datum": datetime.fromtimestamp(p.get("ends_at") or 0, timezone.utc).date(), "sald": sald,
                       "pris": int(pris), "utrop": p.get("estimate"), "delar": delar(titel, beskr), "titel": titel,
                       "url": str(p.get("url") or "").replace("auctionet.com/en/", "auctionet.com/sv/")})
        if sida >= (data.get("pagination") or {}).get("total_pages", 1):
            break
        time.sleep(1)
    return sorted(ut, key=lambda x: x["datum"], reverse=True)


def skriv(fras: str, rader: list[dict]) -> None:
    salda = [r for r in rader if r["sald"]]
    print(f"\n=== \"{fras}\": {len(rader)} avslutade, {len(salda)} sålda, {len(rader) - len(salda)} osålda ===")
    for r in rader:
        per = f"{round(r['pris'] / r['delar']):>5} kr/del" if r["sald"] and r["delar"] > 1 else " " * 13
        status = f"{r['pris']:>7} kr" if r["sald"] else f" osåld (utrop {r['utrop']})"
        print(f"  {r['datum']}  {status:>18}  {r['delar']:>3} delar  {per}  {r['titel'][:90]}")
        print(f"      {r['url']}")
    partier = [r for r in salda if r["delar"] >= 20]
    if partier:
        print(f"  Sålda partier om 20+ delar ({len(partier)}): "
              + ", ".join(f"{r['delar']} delar {r['pris']} kr ({r['datum'].year})" for r in partier))


def main() -> int:
    fraser = sys.argv[1:] or [r.strip() for r in FIL.read_text(encoding="utf-8").splitlines()
                              if r.strip() and not r.startswith("#")]
    for fras in fraser:
        try:
            skriv(fras, hamta(fras))
        except Exception as e:
            print(f"\n=== \"{fras}\": fel – {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
