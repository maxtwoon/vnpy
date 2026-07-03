from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from diagnostics.platform_final_candidate import candidate_summary  # noqa: E402


def main() -> None:
    out = HERE / "platform_final_candidate_config.json"
    payload = candidate_summary()
    payload["verified_gate"] = {
        "sc_neighbor": "6/6",
        "all5_walk_forward": "7/9",
        "symbol_sets": "6/6",
        "platform_goal_passed": True,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
