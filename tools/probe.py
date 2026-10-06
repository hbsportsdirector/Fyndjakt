"""Engångsverktyg: sparar ett riktigt svar från Traderas API så att läsaren kan skrivas mot verkliga fältnamn.
Sparar bara annonsdata (aldrig nycklarna)."""
import json, os, pathlib, requests
UT = pathlib.Path(__file__).parent.parent / "data" / "probe"
UT.mkdir(parents=True, exist_ok=True)
H = {"X-App-Id": os.environ.get("TRADERA_APP_ID", ""), "X-App-Key": os.environ.get("TRADERA_APP_KEY", ""),
     "Accept": "application/json"}
print("Nycklar finns:", bool(H["X-App-Id"]), bool(H["X-App-Key"]))
for namn, params in {"tradera_sok": {"query": "Rörstrand Blå Eld", "pageNumber": 1}}.items():
    try:
        r = requests.get("https://api.tradera.com/v4/search", params=params, headers=H, timeout=30)
        print(namn, r.status_code, len(r.text))
        try:
            data = r.json()
        except ValueError:
            data = {"text": r.text[:3000]}
        (UT / f"{namn}.json").write_text(json.dumps({"status": r.status_code, "svar": data}, ensure_ascii=False, indent=1)[:200000],
                                        encoding="utf-8")
    except Exception as e:
        (UT / f"{namn}.json").write_text(json.dumps({"fel": str(e)}), encoding="utf-8")
        print(namn, "FEL", e)
