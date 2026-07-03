from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DIR = Path(__file__).resolve().parent
ALLOWED = {"stop_loss", "timeout", "trailing_stop", "signal_exit", "risk_exit", "other", "unknown"}


def _walk(value: Any, path: str = "$"):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from _walk(child, f"{path}[{idx}]")


def check_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    checked = 0
    missing = []
    invalid = []
    for loc, obj in _walk(data):
        looks_like_trade = "pnl_pct" in obj and "reason" in obj
        if not looks_like_trade:
            continue
        checked += 1
        code = obj.get("reason_code")
        if code is None:
            missing.append(loc)
        elif code not in ALLOWED:
            invalid.append({"path": loc, "reason_code": code})
    return {"file": str(path), "checked": checked, "missing": missing, "invalid": invalid}


def write_markdown(results: list[dict[str, Any]], out: Path) -> None:
    lines = [
        "# reason_code 报告检查",
        "",
        f"- 允许枚举：{' / '.join(sorted(ALLOWED))}",
        "",
        "| 文件 | 检查交易数 | 缺失 | 非法 | 状态 |",
        "|---|---:|---:|---:|---|",
    ]
    for result in results:
        ok = not result["missing"] and not result["invalid"]
        lines.append(
            f"| `{Path(result['file']).name}` | {result['checked']} | {len(result['missing'])} | {len(result['invalid'])} | {'通过' if ok else '失败'} |"
        )
    lines.append("")
    for result in results:
        if result["missing"] or result["invalid"]:
            lines.append(f"## {Path(result['file']).name}")
            if result["missing"]:
                lines.append("- 缺失：" + " / ".join(result["missing"][:20]))
            if result["invalid"]:
                lines.append("- 非法：" + json.dumps(result["invalid"][:20], ensure_ascii=False))
            lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check reason_code fields in diagnostic JSON reports.")
    parser.add_argument("--paths", nargs="*", type=Path, default=None)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_DIR / "reason_code_report_check.md")
    args = parser.parse_args()

    paths = args.paths
    if not paths:
        paths = sorted(DEFAULT_DIR.glob("*_202*.json"))
    results = [check_file(path) for path in paths if path.exists()]
    write_markdown(results, args.out_md)
    print(f"wrote {args.out_md}")
    failures = [r for r in results if r["missing"] or r["invalid"]]
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
