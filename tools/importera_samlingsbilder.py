"""Laddar upp samlingens bilder till Supabase (bucket `samling`) och fyller i samling_foremal.bilder.

Läser tools/samling-migrering/manifest.json ([{id, n, fil}]) och full/<fil>. Varje bild hamnar som
<user_id>/<id>/<n>.jpg där user_id är Pers (fyndjakt_anvandare där namn = 'Per'). Går att köra om –
bilder skrivs över (upsert) och listan i `bilder` byggs om från manifestet.

Kör:  SUPABASE_URL=… SUPABASE_SERVICE_ROLE_KEY=… python tools/importera_samlingsbilder.py
      (SUPABASE_URL kan utelämnas – då används adressen i config.yaml.)
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


def anslutning() -> tuple[str, str]:
    nyckel = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not nyckel:
        sys.exit("SUPABASE_SERVICE_ROLE_KEY saknas.")
    url = os.getenv("SUPABASE_URL", "").strip()
    if not url:
        with open(ROT / "config.yaml", encoding="utf-8") as f:
            url = (yaml.safe_load(f).get("supabase") or {}).get("url", "")
    if not url:
        sys.exit("SUPABASE_URL saknas (och ingen adress i config.yaml).")
    return url.rstrip("/"), nyckel


def huvuden(nyckel: str, **extra) -> dict:
    return {"apikey": nyckel, "Authorization": f"Bearer {nyckel}", **extra}


def anvandare(url: str, nyckel: str, namn: str = "Per") -> str:
    r = requests.get(f"{url}/rest/v1/fyndjakt_anvandare", params={"namn": f"eq.{namn}", "select": "user_id"},
                     headers=huvuden(nyckel), timeout=30)
    r.raise_for_status()
    rader = r.json()
    if len(rader) != 1:
        sys.exit(f"Hittade {len(rader)} användare med namn {namn!r} – förväntade exakt en.")
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


def main() -> int:
    url, nyckel = anslutning()
    manifest = json.loads((MAPP / "manifest.json").read_text(encoding="utf-8"))
    user_id = anvandare(url, nyckel)
    finns = foremal_ids(url, nyckel, user_id)
    print(f"Användare {user_id[:8]}…, {len(finns)} föremål i databasen, {len(manifest)} bilder i manifestet.")

    per_foremal: dict[str, list[dict]] = {}
    for post in sorted(manifest, key=lambda p: (p["id"], int(p["n"]))):
        per_foremal.setdefault(post["id"], []).append(post)

    uppladdade, saknade, fel = 0, [], []
    for id_, poster in per_foremal.items():
        if id_ not in finns:
            saknade.append(id_)
            continue
        bilder = []
        for post in poster:
            fil = MAPP / "full" / post["fil"]
            n = int(post["n"])
            sokvag = f"{user_id}/{id_}/{n}.jpg"
            try:
                ladda_upp(url, nyckel, sokvag, fil.read_bytes())
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


if __name__ == "__main__":
    sys.exit(main())
