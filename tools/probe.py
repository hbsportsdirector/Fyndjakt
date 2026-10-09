"""Felsökning: gör ett minimalt anrop till Claude med samma nyckel som nattkörningen och sparar svaret
(statuskod och felmeddelande – aldrig nyckeln)."""
import json, os, pathlib, requests
UT = pathlib.Path(__file__).parent.parent / "data" / "probe"
UT.mkdir(parents=True, exist_ok=True)
nyckel = os.environ.get("ANTHROPIC_API_KEY", "")
ut = {"nyckel_finns": bool(nyckel), "nyckel_langd": len(nyckel)}
for modell in ("claude-haiku-4-5-20251001", "claude-sonnet-5-5"):
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
            "x-api-key": nyckel, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": modell, "max_tokens": 5, "messages": [{"role": "user", "content": "Svara: ok"}]})
        ut[modell] = {"status": r.status_code, "svar": r.text[:400]}
    except Exception as e:
        ut[modell] = {"fel": str(e)[:300]}
(UT / "anthropic.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1), encoding="utf-8")
print(ut)
