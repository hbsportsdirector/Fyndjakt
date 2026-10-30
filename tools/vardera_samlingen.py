"""Omvärderar samlingen mot sålda föremål på Auctionet (se vardering.py) och sparar resultatet i Supabase.

Föremål utan sökord får ett av Claude (billig textfråga). Värdet uppdateras bara med minst 3 sålda jämförelser;
det gamla värdet sparas i prishistoriken. Skriver ut de största ändringarna och föremålen med tunt underlag.

Kör:  FYNDJAKT_BOT_TOKEN=… ANTHROPIC_API_KEY=… python tools/vardera_samlingen.py [--torr]
      --torr: räknar och skriver ut, men sparar inget.
"""
import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main  # noqa: E402
import prisjamforelse  # noqa: E402
import smak  # noqa: E402
import vardering  # noqa: E402


def rpc(ans, namn: str, **args):
    url, nyckel, token = ans
    r = requests.post(f"{url}/rest/v1/rpc/{namn}", json={"token": token, **args},
                      headers={"apikey": nyckel, "Content-Type": "application/json"}, timeout=120)
    r.raise_for_status()
    return r.json()


def sokfras(f: dict, cfg: dict, klient) -> str:
    """Föremålets sökord, eller ett nytt från Claude (tillverkare/formgivare + serie + föremålstyp)."""
    if (f.get("sokord") or "").strip():
        return f["sokord"].strip()
    import bedomning
    titel = ", ".join(x for x in (f.get("namn"), f.get("tillverkare"), f.get("serie"), f.get("kategori"))
                      if x and x != "Okänd")
    return bedomning.foresla_jamforsok(titel, cfg["modell"], klient)


def main_() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--torr", action="store_true", help="Spara inget")
    args = p.parse_args()
    cfg = main.las_config()
    ans = smak._anslutning(cfg)
    if not ans:
        sys.exit("FYNDJAKT_BOT_TOKEN saknas.")
    foremal = rpc(ans, "samling_varde_underlag")
    print(f"{len(foremal)} föremål att värdera.")

    klient = None
    if any(not (f.get("sokord") or "").strip() for f in foremal):
        import bedomning
        klient = bedomning._klient()
    fraser = {f["id"]: sokfras(f, cfg, klient) for f in foremal}

    def en(f):
        fras = fraser[f["id"]]
        try:
            return f, fras, vardering.vardera(f, prisjamforelse.avslutade(fras)), None
        except Exception as e:  # en trasig sökning ska inte stoppa resten
            return f, fras, None, e

    resultat = []
    with ThreadPoolExecutor(3) as pool:
        for f, fras, res, fel in pool.map(en, foremal):
            if fel:
                print(f"  FEL {f['id']}: {fel}")
                continue
            resultat.append((f, fras, res))
            time.sleep(0.2)

    # Bara säkra värderingar ändras automatiskt (vardering.beslut); resten är förslag att granska.
    beslut = {f["id"]: vardering.beslut(f, res, fras) for f, fras, res in resultat}
    poster = [{"id": f["id"], "fras": fras, "uppdatera": beslut[f["id"]][0], "text": res["text"],
               "forslag": not beslut[f["id"]][0] and vardering.foreslas(res, beslut[f["id"]][1], f.get("auk_median")),
               "skal": beslut[f["id"]][1], "url": vardering.sok_url(fras), "median": res.get("median"),
               "lag": res.get("lag"), "hog": res.get("hog"), "antal": res["antal"]} for f, fras, res in resultat]

    def rad(f, fras, res, skal=""):
        gammal = f.get("auk_median")
        nytt = res.get("median")
        return (f"  {f['id']:42} {gammal if gammal is not None else '–':>6} → {nytt if nytt is not None else '–':>6} kr"
                f"   sökte \"{fras}\"{'   [' + skal + ']' if skal else ''}\n      {res['text']}")
    andrade = [(f, fras, res) for f, fras, res in resultat if beslut[f["id"]][0]]
    forslag = [(f, fras, res) for f, fras, res in resultat if not beslut[f["id"]][0] and res["uppdatera"]]
    tunna = [(f, fras, res) for f, fras, res in resultat if not res["uppdatera"]]
    print(f"\nNytt värde för {len(andrade)} föremål:")
    for t in andrade:
        print(rad(*t))
    print(f"\nInte ändrat automatiskt ({len(forslag)}) – de som inte är partier eller låsta blir förslag på sajten:")
    for f, fras, res in forslag:
        print(rad(f, fras, res, beslut[f["id"]][1]))
    print(f"\nTunt underlag – värdet inte ändrat ({len(tunna)}):")
    for f, fras, res in tunna:
        print(f"  {f['id']:42} sökte \"{fras}\": {res['antal']} sålda, {res['osalda']} osålda")

    if args.torr:
        print("\nTorrkörning – inget sparat.")
        return 0
    n = rpc(ans, "samling_varde_spara", poster=poster)
    print(f"\nSparat: {n} föremål fick nytt värde, {sum(p['forslag'] for p in poster)} förslag att granska på sajten.")
    return 0


if __name__ == "__main__":
    sys.exit(main_())
