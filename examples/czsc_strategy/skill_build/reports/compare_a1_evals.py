from __future__ import annotations

import argparse
import json
from pathlib import Path


TERMS = [
    "离开段", "进入段", "回抽不入中枢", "中枢震荡", "背驰", "底分型", "顶分型", "强整理", "温和调整",
    "中枢上方", "中枢下方", "中枢内", "一买", "二买", "三买", "一卖", "二卖", "三卖",
]


def _rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _text(row: dict) -> str:
    return row.get("llm_text", "") or row.get("generated", "") or ""


def metrics(rows: list[dict]) -> dict:
    n = len(rows) or 1
    scenario = sum(r.get("llm_score", {}).get("scenario_count", 0) for r in rows) / n
    unsourced = sum(len(r.get("llm_score", {}).get("unsourced_prices", []) or []) for r in rows)
    invented = sum(len(r.get("llm_score", {}).get("invented_confirmed_bsp", []) or []) for r in rows)
    missing_div = [r.get("date") for r in rows if "背驰" not in _text(r)]
    term_total = 0
    term_unique = 0
    for row in rows:
        hits = {term: _text(row).count(term) for term in TERMS if _text(row).count(term)}
        term_total += sum(hits.values())
        term_unique += len(hits)
    return {
        "rows": len(rows),
        "scenario": scenario,
        "unsourced": unsourced,
        "invented": invented,
        "missing_div": missing_div,
        "avg_term_total": term_total / n,
        "avg_term_unique": term_unique / n,
    }


def write(old_path: Path, new_path: Path, out: Path) -> None:
    old = metrics(_rows(old_path))
    new = metrics(_rows(new_path))
    lines = [
        "# A1 评估对比",
        "",
        f"- 旧版：`{old_path.name}`",
        f"- 新版：`{new_path.name}`",
        "",
        "| 指标 | 旧版 | 新版 |",
        "|---|---:|---:|",
        f"| 样本数 | {old['rows']} | {new['rows']} |",
        f"| 平均情景数 | {old['scenario']:.2f} | {new['scenario']:.2f} |",
        f"| 未溯源价位数 | {old['unsourced']} | {new['unsourced']} |",
        f"| 编造确认买卖点数 | {old['invented']} | {new['invented']} |",
        f"| 背驰缺失天数 | {len(old['missing_div'])} | {len(new['missing_div'])} |",
        f"| 平均术语次数 | {old['avg_term_total']:.2f} | {new['avg_term_total']:.2f} |",
        f"| 平均术语种类 | {old['avg_term_unique']:.2f} | {new['avg_term_unique']:.2f} |",
        "",
        "## 新版背驰缺失日期",
        "",
        " / ".join(new["missing_div"]) if new["missing_div"] else "无",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two A1 true-skill evaluation JSONL files.")
    parser.add_argument("--old", type=Path, default=Path(__file__).with_name("A1_true_skill_eval_50days.jsonl"))
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("A1_eval_comparison.md"))
    args = parser.parse_args()
    write(args.old, args.new, args.out_md)


if __name__ == "__main__":
    main()
