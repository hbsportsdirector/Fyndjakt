"""Genererar supabase/functions/fyndjakt-snabbstart/index.ts från mall.ts, så att snabbstarten
använder exakt samma bedömningsinstruktion, regler och regioner som nattkörningen."""
import json
import sys
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT))
import bedomning  # noqa: E402
import main  # noqa: E402
import sajt  # noqa: E402

cfg = main.las_config()
mapp = ROT / "supabase" / "functions" / "fyndjakt-snabbstart"
ts = (mapp / "mall.ts").read_text(encoding="utf-8")
ersatt = {
    "__MODELL__": cfg["modell"],
    "__INSTRUKTION__": bedomning.INSTRUKTION.replace("{{", "{").replace("}}", "}"),
    "__KALIBRERING__": cfg.get("bedomningsregler_anvandare") or bedomning.STANDARD_KALIBRERING,
    "__REGIONER__": {ort: reg for reg, orter in sajt.REGIONER.items() for ort in orter},
    "__UTESLUT__": [o.lower() for o in cfg.get("uteslut_ord", [])],
    "__MIN_BETYG__": cfg.get("sajt_min_betyg", 8),
    "__MAX_PER_SOKORD__": cfg.get("sajt_max_per_sokord", 3),
}
for k, v in ersatt.items():
    ts = ts.replace(k, json.dumps(v, ensure_ascii=False))
(mapp / "index.ts").write_text(ts, encoding="utf-8")
print("Skrev", mapp / "index.ts")
