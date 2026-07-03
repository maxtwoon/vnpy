from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_JSONL = Path(__file__).resolve().with_name("A1_true_skill_eval_50days.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check A1 true-skill evaluation quality gate.")
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--max-unsourced-prices", type=int, default=0)
    parser.add_argument("--min-avg-scenario", type=float, default=8.0)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit(f"No rows in {args.jsonl}")

    bad_status = [r["date"] for r in rows if r.get("status") != "ok"]
    empty_text = [r["date"] for r in rows if not (r.get("llm_text") or "").strip()]
    invented = [
        (r["date"], r.get("llm_score", {}).get("invented_confirmed_bsp", []))
        for r in rows
        if r.get("llm_score", {}).get("invented_confirmed_bsp")
    ]
    unsourced = [
        (r["date"], r.get("llm_score", {}).get("unsourced_prices", []))
        for r in rows
        if r.get("llm_score", {}).get("unsourced_prices")
    ]
    missing_attr = [r["date"] for r in rows if not r.get("llm_score", {}).get("direction_attribution")]
    avg_scenario = sum(r.get("llm_score", {}).get("scenario_count", 0) for r in rows) / len(rows)

    errors = []
    if bad_status:
        errors.append(f"status not ok: {bad_status}")
    if empty_text:
        errors.append(f"empty llm_text: {empty_text}")
    if invented:
        errors.append(f"invented confirmed buy/sell points: {invented}")
    unsourced_count = sum(len(values) for _, values in unsourced)
    if unsourced_count > args.max_unsourced_prices:
        errors.append(f"unsourced prices {unsourced_count} > {args.max_unsourced_prices}: {unsourced}")
    if missing_attr:
        errors.append(f"missing direction_attribution: {missing_attr}")
    if avg_scenario < args.min_avg_scenario:
        errors.append(f"avg scenario_count {avg_scenario:.2f} < {args.min_avg_scenario:.2f}")

    print(f"rows={len(rows)}")
    print(f"avg_scenario={avg_scenario:.2f}")
    print(f"unsourced_prices={unsourced_count}")
    print(f"invented_confirmed_bsp={sum(len(values) for _, values in invented)}")
    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        raise SystemExit(1)
    print("A1 eval gate passed")


if __name__ == "__main__":
    main()
