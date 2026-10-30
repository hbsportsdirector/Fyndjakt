"""Laddar upp samlingens bilder till Supabase (bucket `samling`) och fyller i samling_foremal.bilder.

Läser tools/samling-migrering/manifest.json ([{id, n, fil}]) och full/<fil>. Varje bild hamnar som
<user_id>/<id>/<n>.jpg där user_id är Pers (fyndjakt_anvandare där namn = 'Per'). Går att köra om –
bilder skrivs över (upsert) och listan i `bilder` byggs om från manifestet.

Två vägar:
- Med SUPABASE_SERVICE_ROLE_KEY: laddar upp direkt till Storage och uppdaterar tabellen via REST.
- Annars med FYNDJAKT_BOT_TOKEN (nattkörningens nyckel): ber edge-funktionen fyndjakt-kann-igen
  (typ "importera_bilder") hämta bilderna från repot på GitHub (raw.githubusercontent.com) och lägga in dem –
  funktionen har servicenyckeln. Kräver att bilderna ligger på GitHub (GITHUB_REPOSITORY och GITHUB_SHA sätts
  av Actions; annars BILD_BAS_URL).

Kör:  SUPABASE_SERVICE_ROLE_KEY=… python tools/importera_samlingsbilder.py
      FYNDJAKT_BOT_TOKEN=… GITHUB_REPOSITORY=hbsportsdirector/Fyndjakt GITHUB_SHA=… python tools/importera_samlingsbilder.py
"""
import json
import os
import sys
from pathlib import Path

import requests
import yaml

ROT = Path(__file__).resolve().parent.parent
MAPP = ROT / "tools" / "samling-migrering"
BUCKET = "samling"
ANVANDARE = "Per"


def konfig() -> dict:
    with open(ROT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f).get("supabase") or {}


def supabase_url() -> str:
    url = os.getenv("SUPABASE_URL", "").strip() or konfig().get("url", "")
    if not url:
        sys.exit("SUPABASE_URL saknas (och ingen adress i config.yaml).")
    return url.rstrip("/")


def manifest() -> dict[str, list[dict]]:
    """{id: [{n, fil}, ...]} sorterat på n."""
    per: dict[str, list[dict]] = {}
    for post in sorted(json.loads((MAPP / "manifest.json").read_text(encoding="utf-8")), key=lambda p: (p["id"], int(p["n"]))):
        per.setdefault(post["id"], []).append(post)
    return per


# ── Väg 1: servicenyckeln direkt ──────────────────────────────────────

def huvuden(nyckel: str, **extra) -> dict:
    return {"apikey": nyckel, "Authorization": f"Bearer {nyckel}", **extra}


def anvandare(url: str, nyckel: str) -> str:
    r = requests.get(f"{url}/rest/v1/fyndjakt_anvandare", params={"namn": f"eq.{ANVANDARE}", "select": "user_id"},
                     headers=huvuden(nyckel), timeout=30)
    r.raise_for_status()
    rader = r.json()
    if len(rader) != 1:
        sys.exit(f"Hittade {len(rader)} användare med namn {ANVANDARE!r} – förväntade exakt en.")
    return rader[0]["user_id"]


def foremal_ids(url: str, nyckel: str, user_id: str) -> set[str]:
    r = requests.get(f"{url}/rest/v1/samling_foremal", params={"user_id": f"eq.{user_id}", "select": "id"},
                     headers=huvuden(nyckel), timeout=30)
    r.raise_for_status()
    return {x["id"] for x in r.json()}


def ladda_upp(url: str, nyckel: str, sokvag: str, data: bytes) -> None:
    r = requests.post(f"{url}/storage/v1/object/{BUCKET}/{sokvag}", data=data, timeout=120,
                      headers=huvuden(nyckel, **{"Content-Type": "image/jpeg", "x-upsert": "true",
                                                  "Cache-Control": "max-age=3600"}))
    if r.status_code >= 300:
        raise RuntimeError(f"{r.status_code}: {r.text[:200]}")


def spara_bilder(url: str, nyckel: str, id_: str, bilder: list[dict]) -> None:
    r = requests.patch(f"{url}/rest/v1/samling_foremal", params={"id": f"eq.{id_}"}, json={"bilder": bilder},
                       headers=huvuden(nyckel, **{"Content-Type": "application/json", "Prefer": "return=minimal"}),
                       timeout=30)
    r.raise_for_status()


def importera_direkt(url: str, nyckel: str) -> int:
    per_foremal = manifest()
    user_id = anvandare(url, nyckel)
    finns = foremal_ids(url, nyckel, user_id)
    print(f"Användare {user_id[:8]}…, {len(finns)} föremål i databasen, {len(per_foremal)} föremål i manifestet.")
    uppladdade, saknade, fel = 0, [], []
    for id_, poster in per_foremal.items():
        if id_ not in finns:
            saknade.append(id_)
            continue
        bilder = []
        for post in poster:
            n = int(post["n"])
            sokvag = f"{user_id}/{id_}/{n}.jpg"
            try:
                ladda_upp(url, nyckel, sokvag, (MAPP / "full" / post["fil"]).read_bytes())
            except Exception as e:  # en trasig bild ska inte stoppa resten
                fel.append(f"{sokvag}: {e}")
                continue
            bilder.append({"n": n, "path": sokvag})
            uppladdade += 1
        if bilder:
            spara_bilder(url, nyckel, id_, bilder)
            print(f"  {id_:40} {len(bilder)} bild(er)")
    print(f"\nKlart: {uppladdade} bilder uppladdade för {len(per_foremal) - len(saknade)} föremål.")
    if saknade:
        print(f"Finns inte i samling_foremal (hoppade över): {', '.join(saknade)}")
    for f in fel:
        print(f"FEL {f}")
    return 1 if fel else 0


# ── Väg 2: edge-funktionen hämtar bilderna från GitHub ────────────────

def bild_bas_url() -> str:
    bas = os.getenv("BILD_BAS_URL", "").strip()
    if bas:
        return bas.rstrip("/")
    repo, sha = os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_SHA", "")
    if not (repo and sha):
        sys.exit("Utan SUPABASE_SERVICE_ROLE_KEY behövs bilderna på GitHub: sätt GITHUB_REPOSITORY och GITHUB_SHA (eller BILD_BAS_URL).")
    return f"https://raw.githubusercontent.com/{repo}/{sha}/tools/samling-migrering/full"


def importera_via_funktion(url: str, token: str) -> int:
    bas = bild_bas_url()
    poster = [{"id": id_, "n": int(p["n"]), "url": f"{bas}/{p['fil']}"} for id_, lista in manifest().items() for p in lista]
    # Gatewayn vill ha en nyckel i Authorization – den publika nyckeln (SUPABASE_ANON_KEY går också bra).
    anon = os.getenv("SUPABASE_ANON_KEY", "").strip() or konfig().get("nyckel", "")
    print(f"Ber fyndjakt-kann-igen hämta {len(poster)} bilder från {bas} …")
    r = requests.post(f"{url}/functions/v1/fyndjakt-kann-igen",
                      json={"typ": "importera_bilder", "token": token, "anvandare": ANVANDARE, "poster": poster},
                      headers={"apikey": anon, "Authorization": f"Bearer {anon}", "Content-Type": "application/json"}, timeout=600)
    if r.status_code >= 300:
        print(f"Funktionen svarade {r.status_code}: {r.text[:500]}")
        return 1
    res = r.json()
    for id_, n in sorted((res.get("resultat") or {}).items()):
        print(f"  {id_:40} {n} bild(er)")
    print(f"\nKlart: {res.get('bilder')} bilder för {res.get('foremal')} föremål (användare {str(res.get('user_id'))[:8]}…).")
    if res.get("saknade"):
        print(f"Finns inte i samling_foremal (hoppade över): {', '.join(res['saknade'])}")
    fel = [id_ for id_, n in (res.get("resultat") or {}).items() if not n]
    if fel:
        print(f"Inga bilder kunde läggas in för: {', '.join(fel)}")
    return 1 if fel else 0


def main() -> int:
    url = supabase_url()
    service = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if service:
        return importera_direkt(url, service)
    token = os.getenv("FYNDJAKT_BOT_TOKEN", "").strip()
    if token:
        return importera_via_funktion(url, token)
    sys.exit("Varken SUPABASE_SERVICE_ROLE_KEY eller FYNDJAKT_BOT_TOKEN är satt.")


if __name__ == "__main__":
    sys.exit(main())
