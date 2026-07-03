from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent


GOAL = {
    "min_sc_neighbor_pass": 4,
    "sc_neighbor_total": 6,
    "min_walk_forward_positive": 7,
    "walk_forward_total": 9,
    "min_symbol_set_pass": 4,
    "symbol_set_total": 6,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sc_neighbor_status(path: Path) -> dict[str, Any]:
    payload = _load(path)
    rows = payload.get("multipliers", {})
    pass_count = sum(1 for row in rows.values() if row.get("goal_status", {}).get("passed"))
    return {
        "path": str(path),
        "pass_count": pass_count,
        "total": len(rows),
        "passed": pass_count >= GOAL["min_sc_neighbor_pass"] and len(rows) == GOAL["sc_neighbor_total"],
    }


def _symbol_set_status(path: Path, candidate: str = "block_daily_down") -> dict[str, Any]:
    payload = _load(path)
    row = payload.get("rows", {}).get(candidate)
    if row is None:
        raise KeyError(f"candidate {candidate!r} not found in {path}")
    symbol_sets = row.get("symbol_sets", {})
    pass_count = sum(1 for item in symbol_sets.values() if item.get("goal_status", {}).get("passed"))
    all5_wf = row.get("all5", {}).get("walk_forward", {})
    positive = int(all5_wf.get("positive_windows", 0))
    total = int(all5_wf.get("total_windows", 0))
    return {
        "path": str(path),
        "candidate": candidate,
        "walk_forward_positive": positive,
        "walk_forward_total": total,
        "walk_forward_passed": positive >= GOAL["min_walk_forward_positive"] and total == GOAL["walk_forward_total"],
        "symbol_set_pass_count": pass_count,
        "symbol_set_total": len(symbol_sets),
        "symbol_set_passed": pass_count >= GOAL["min_symbol_set_pass"] and len(symbol_sets) == GOAL["symbol_set_total"],
    }


def build_status(sc_neighbor: Path, symbol_sets: Path, candidate: str) -> dict[str, Any]:
    sc = _sc_neighbor_status(sc_neighbor)
    sym = _symbol_set_status(symbol_sets, candidate)
    checks = {
        "sc_neighbor_ge_4_of_6": sc["passed"],
        "walk_forward_ge_7_of_9": sym["walk_forward_passed"],
        "symbol_sets_ge_4_of_6": sym["symbol_set_passed"],
    }
    return {
        "goal": GOAL,
        "sc_neighbor": sc,
        "symbol_sets": sym,
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the quantified platform stability goal.")
    parser.add_argument(
        "--sc-neighbor",
        type=Path,
        default=HERE / "sc_short_weight_neighborhood_first_buy_gate.json",
    )
    parser.add_argument(
        "--symbol-sets",
        type=Path,
        default=HERE / "first_buy_environment_candidates_block_daily_down_075_6sets.json",
    )
    parser.add_argument("--candidate", default="block_daily_down")
    parser.add_argument("--out-json", type=Path, default=HERE / "platform_stability_goal_status.json")
    args = parser.parse_args()

    status = build_status(args.sc_neighbor, args.symbol_sets, args.candidate)
    args.out_json.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    sc = status["sc_neighbor"]
    sym = status["symbol_sets"]
    print(f"sc_neighbor={sc['pass_count']}/{sc['total']} required>=4/6 pass={sc['passed']}")
    print(
        "walk_forward="
        f"{sym['walk_forward_positive']}/{sym['walk_forward_total']} required>=7/9 "
        f"pass={sym['walk_forward_passed']}"
    )
    print(
        "symbol_sets="
        f"{sym['symbol_set_pass_count']}/{sym['symbol_set_total']} required>=4/6 "
        f"pass={sym['symbol_set_passed']}"
    )
    print(f"platform_goal_passed={status['passed']}")
    if not status["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
