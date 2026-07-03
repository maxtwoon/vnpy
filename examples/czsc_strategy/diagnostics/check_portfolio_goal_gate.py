from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_CHECKS = [
    "trades_ge_100",
    "pf_ge_1_2",
    "drawdown_le_20",
    "sharpe_ge_0_5",
    "calmar_ge_0_5",
    "walk_forward_ge_2_3",
    "risk_adjusted_gt_buy_hold",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Assert portfolio hard-goal gate passes.")
    parser.add_argument(
        "--json",
        type=Path,
        default=Path(__file__).with_name("portfolio_goal_expanded_short_sc_0847.json"),
    )
    args = parser.parse_args()

    payload = json.loads(args.json.read_text(encoding="utf-8"))
    status = payload["goal_status"]
    checks = status["checks"]
    missing = [name for name in REQUIRED_CHECKS if name not in checks]
    failed = [name for name in REQUIRED_CHECKS if not checks.get(name)]
    if missing or failed or not status.get("passed"):
        raise SystemExit(
            "portfolio goal gate failed: "
            f"missing={missing}, failed={failed}, passed={status.get('passed')}"
        )

    metrics = payload["out_sample"]["metrics"]
    benchmark = payload["out_sample"]["buy_hold"]
    print("portfolio goal gate passed")
    print(f"scenario={payload['scenario']}")
    print(f"trades={metrics['trades']}")
    print(f"profit_factor={metrics['profit_factor']:.4f}")
    print(f"max_drawdown_pct={metrics['max_drawdown_pct']:.4f}")
    print(f"sharpe={metrics['sharpe']:.4f}")
    print(f"calmar={metrics['calmar']:.4f}")
    print(f"walk_forward={payload['walk_forward']['positive_windows']}/{payload['walk_forward']['total_windows']}")
    print(f"buy_hold_sharpe={benchmark['sharpe']:.4f}")
    print(f"buy_hold_calmar={benchmark['calmar']:.4f}")


if __name__ == "__main__":
    main()
