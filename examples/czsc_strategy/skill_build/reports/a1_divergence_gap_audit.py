from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_JSONL = Path(__file__).with_name("A1_true_skill_eval_50days_divergence.jsonl")
DEFAULT_OUT = Path(__file__).with_name("A1_divergence_gap_audit.md")
TARGET_DATES = ["2025-08-11", "2026-03-10", "2026-06-10"]
DIVERGENCE_SYNONYMS = ["背驰", "力度衰减", "衰竭", "动能减弱", "力度不足", "盘背"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit remaining A1 divergence wording gaps.")
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_date = {r["date"]: r for r in rows}
    lines = [
        "# A1 背驰缺失专项审计",
        "",
        f"- JSONL：`{args.jsonl.name}`",
        f"- 同义词：{' / '.join(DIVERGENCE_SYNONYMS)}",
        "",
        "| 日期 | 含“背驰” | 含同义词 | 客观背驰 | 判定 |",
        "|---|---|---|---|---|",
    ]
    for date in TARGET_DATES:
        row = by_date.get(date)
        if not row:
            lines.append(f"| {date} | - | - | - | 缺少样本 |")
            continue
        text = row.get("llm_text", "")
        has_exact = "背驰" in text
        synonyms = [term for term in DIVERGENCE_SYNONYMS if term in text and term != "背驰"]
        daily = row.get("objective", {}).get("levels", {}).get("日线", {})
        objective_div = daily.get("背驰")
        verdict = "指标漏识别" if synonyms and not has_exact else ("模型未写" if not has_exact else "已覆盖")
        lines.append(f"| {date} | {has_exact} | {' / '.join(synonyms) or '-'} | {objective_div} | {verdict} |")
        lines.extend(["", f"## {date}", "", text[:1200], ""])
    args.out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
