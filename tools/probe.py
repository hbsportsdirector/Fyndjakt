"""Felsökning: finns säljarens ort i Traderas API (annonsdetaljer eller användarinfo)?
Sparar bara statuskoder och fältnamn/ort – aldrig nycklar."""
import json, os, pathlib, requests
UT = pathlib.Path(__file__).parent.parent / "data" / "probe"
UT.mkdir(parents=True, exist_ok=True)
H = {"X-App-Id": os.environ.get("TRADERA_APP_ID", ""), "X-App-Key": os.environ.get("TRADERA_APP_KEY", ""),
     "Accept": "application/json"}
ut = {}
s = requests.get("https://api.tradera.com/v4/search", params={"query": "Blå Eld", "pageNumber": 1}, headers=H, timeout=30)
ut["search_status"] = s.status_code
poster = []
try:
    d = s.json()
    poster = d.get("items") or d.get("Items") or []
except ValueError:
    pass
if poster:
    it = poster[0]
    iid, sid = it.get("id"), it.get("sellerId")
    ut["item_id"], ut["seller_id"] = iid, sid
    for namn, url in {
        "items_id": f"https://api.tradera.com/v4/items/{iid}",
        "items_q": f"https://api.tradera.com/v4/items?itemId={iid}",
        "item_id": f"https://api.tradera.com/v4/item/{iid}",
        "users_id": f"https://api.tradera.com/v4/users/{sid}",
        "user_id": f"https://api.tradera.com/v4/user/{sid}",
        "members_id": f"https://api.tradera.com/v4/members/{sid}",
    }.items():
        try:
            r = requests.get(url, headers=H, timeout=30)
            info = {"status": r.status_code, "borjan": r.text[:200]}
            try:
                j = r.json()
                info["falt"] = sorted(j.keys()) if isinstance(j, dict) else str(type(j))
                txt = json.dumps(j, ensure_ascii=False)
                for k in ("city", "City", "location", "Location", "zip", "postalCode", "address", "Address"):
                    i = txt.find(f'"{k}"')
                    if i >= 0:
                        info.setdefault("ort", []).append(txt[i:i + 120])
            except ValueError:
                pass
            ut[namn] = info
        except Exception as e:
            ut[namn] = {"fel": str(e)[:200]}
(UT / "tradera_ort.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(ut, ensure_ascii=False)[:3000])
