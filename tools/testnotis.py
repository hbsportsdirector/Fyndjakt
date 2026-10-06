"""Skickar en testnotis till administratörens enheter (för att kontrollera att notiserna fungerar)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main  # noqa: E402
import smak  # noqa: E402
import webbnotis  # noqa: E402

cfg = main.las_config()
export = smak.hamta(cfg) or {}
admins = smak.admins(export)
for pren in [p for p in export.get("push", []) if p["user_id"] in admins]:
    status = webbnotis.skicka(pren, {"title": "Fyndjakt", "body": "Testnotis – notiserna fungerar! Nästa kommer när natten gett nya toppfynd.",
                                     "url": webbnotis.AVSANDARE, "tag": "fyndjakt-test"}, export["vapid"])
    print("Testnotis:", status)
