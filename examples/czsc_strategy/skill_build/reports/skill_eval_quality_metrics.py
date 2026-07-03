from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_JSONL = Path(__file__).resolve().with_name("A1_true_skill_eval_50days.jsonl")
DEFAULT_OUT = Path(__file__).resolve().with_name("A1_quality_metrics.md")

CHAN_TERMS = [
    "离开段",
    "进入段",
    "回抽不入中枢",
    "中枢震荡",
    "背驰",
    "底分型",
    "顶分型",
    "强整理",
    "温和调整",
    "中枢上方",
    "中枢下方",
    "中枢内",
    "一买",
    "二买",
    "三买",
    "一卖",
    "二卖",
    "三卖",
]

STRUCTURE_ITEMS = {
    "方向": ["方向", "向上", "向下", "趋势"],
    "中枢": ["中枢", "ZG", "ZD"],
    "背驰": ["背驰"],
    "买卖点": ["一买", "二买", "三买", "一卖", "二卖", "三卖", "买卖点"],
    "后续情景": ["第一种", "第二种", "情景", "推演"],
}


def _load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _text(row: dict[str, Any]) -> str:
    return row.get("llm_text", "") or ""


def _term_hits(text: str) -> dict[str, int]:
    return {term: text.count(term) for term in CHAN_TERMS if text.count(term)}


def _structure_score(text: str) -> dict[str, bool]:
    return {
        item: any(token in text for token in tokens)
        for item, tokens in STRUCTURE_ITEMS.items()
    }


def _sentence_count(text: str) -> int:
    parts = re.split(r"[。！？\n]+", text)
    return len([p for p in parts if p.strip()])


def compute(rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for row in rows:
        text = _text(row)
        hits = _term_hits(text)
        structure = _structure_score(text)
        sentence_count = max(_sentence_count(text), 1)
        items.append(
            {
                "date": row.get("date"),
                "status": row.get("status"),
                "term_total": sum(hits.values()),
                "term_unique": len(hits),
                "term_density": sum(hits.values()) / sentence_count,
                "structure_score": sum(1 for ok in structure.values() if ok),
                "structure_total": len(structure),
                "structure": structure,
                "score": row.get("llm_score", {}),
            }
        )

    n = len(items) or 1
    term_freq: dict[str, int] = {}
    for row in rows:
        for term, count in _term_hits(_text(row)).items():
            term_freq[term] = term_freq.get(term, 0) + count

    missing = {
        item: [x["date"] for x in items if not x["structure"][item]]
        for item in STRUCTURE_ITEMS
    }

    return {
        "rows": len(rows),
        "avg_term_total": sum(x["term_total"] for x in items) / n,
        "avg_term_unique": sum(x["term_unique"] for x in items) / n,
        "avg_term_density": sum(x["term_density"] for x in items) / n,
        "avg_structure_score": sum(x["structure_score"] for x in items) / n,
        "structure_total": len(STRUCTURE_ITEMS),
        "term_freq": dict(sorted(term_freq.items(), key=lambda kv: (-kv[1], kv[0]))),
        "missing": missing,
        "items": items,
    }


def write_markdown(metrics: dict[str, Any], out: Path) -> None:
    lines = [
        "# A1 Skill 质量指标",
        "",
        f"- 样本数：{metrics['rows']}",
        f"- 平均术语出现次数：{metrics['avg_term_total']:.2f}",
        f"- 平均术语种类数：{metrics['avg_term_unique']:.2f}",
        f"- 平均术语密度：{metrics['avg_term_density']:.2f} / 句",
        f"- 平均结构完整性：{metrics['avg_structure_score']:.2f} / {metrics['structure_total']}",
        "",
        "## 术语频次",
        "",
        "| 术语 | 次数 |",
        "|---|---:|",
    ]
    for term, count in metrics["term_freq"].items():
        lines.append(f"| {term} | {count} |")

    lines.extend(["", "## 结构完整性缺口", ""])
    for item, dates in metrics["missing"].items():
        sample = " / ".join(dates[:10])
        suffix = " ..." if len(dates) > 10 else ""
        lines.append(f"- {item}：缺失 {len(dates)} 天。{sample}{suffix}")

    lines.extend(
        [
            "",
            "## 逐日指标",
            "",
            "| 日期 | 状态 | 术语次数 | 术语种类 | 术语密度 | 结构完整性 | 方向归因 |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for item in metrics["items"]:
        score = item.get("score", {})
        lines.append(
            "| {date} | {status} | {term_total} | {term_unique} | {density:.2f} | {structure}/{total} | {attr} |".format(
                date=item["date"],
                status=item["status"],
                term_total=item["term_total"],
                term_unique=item["term_unique"],
                density=item["term_density"],
                structure=item["structure_score"],
                total=item["structure_total"],
                attr=score.get("direction_attribution", "-"),
            )
        )
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute A1 true-skill term density and structural completeness.")
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    metrics = compute(_load_rows(args.jsonl))
    write_markdown(metrics, args.out_md)
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
