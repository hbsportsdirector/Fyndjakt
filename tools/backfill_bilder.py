"""Skapar miniatyrer (fyndjakt_bilder) för alla fynd som redan ligger i fyndjakt_fynd. Körs en gång;
därefter sköter nattkörningen det. Går att köra om – fynd som redan har en miniatyr hoppas över.

Kör:  FYNDJAKT_BOT_TOKEN=… python tools/backfill_bilder.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bilder  # noqa: E402
import main  # noqa: E402

cfg = main.las_config()
if not bilder.smak._anslutning(cfg):
    sys.exit("FYNDJAKT_BOT_TOKEN saknas.")
bilder.synka(cfg, paus=0.3)
