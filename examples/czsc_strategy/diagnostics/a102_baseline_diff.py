"""
A102 AC1 基线字节一致验证（只读诊断）
=====================================
方法：同一 RB888 默认配置回测，分别用改动前（git stash）与改动后（HEAD工作区）
代码运行，对 generate_report() 输出做 JSON 级 diff。默认配置
（trade_freq="30分钟", filter_freq="日线"）下 A102 必须字节一致。

用法：
  python diagnostics/a102_baseline_diff.py run <out.json>   # 跑一次并落盘
  python diagnostics/a102_baseline_diff.py diff <old.json> <new.json>  # 对比

铁律：只读；RESEARCH-ONLY；不作为盈利能力证明。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# diff 时排除的易变字段（时间戳类）
VOLATILE_KEYS = {"generated_at", "report_generated_at", "created_at", "timestamp"}


def run(out_path: str) -> int:
    from chan_strategy.backtest_engine import BacktestEngine

    engine = BacktestEngine("RB888", table_name="rb888_1M_raw")  # 默认 BACKTEST_CONFIG 窗口与成本
    report = engine.run()
    Path(out_path).write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print(f"落盘: {out_path}")
    return 0 if "error" not in report else 1


def _flatten(obj, prefix=""):
    items = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in VOLATILE_KEYS:
                continue
            items.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            items.update(_flatten(v, f"{prefix}{i}."))
    else:
        items[prefix.rstrip(".")] = obj
    return items


def diff(old_path: str, new_path: str) -> int:
    old = _flatten(json.loads(Path(old_path).read_text(encoding="utf-8")))
    new = _flatten(json.loads(Path(new_path).read_text(encoding="utf-8")))
    keys = sorted(set(old) | set(new))
    diffs = []
    for k in keys:
        if old.get(k, "<MISSING>") != new.get(k, "<MISSING>"):
            diffs.append((k, old.get(k, "<MISSING>"), new.get(k, "<MISSING>")))

    out_md = Path(__file__).parent / "a102_baseline_diff_rb888_20260729.md"
    lines = [
        "# A102 AC1 基线字节一致验证：RB888 默认配置回测 diff",
        "",
        "<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->",
        "",
        "> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**",
        "",
        f"- old（改动前 stash）: `{old_path}`",
        f"- new（改动后工作区）: `{new_path}`",
        f"- 扁平化键数: old={len(old)}, new={len(new)}",
        f"- **差异条数: {len(diffs)}**",
        "",
    ]
    if diffs:
        lines += ["| 键 | old | new |", "|----|-----|-----|"]
        for k, o, n in diffs[:200]:
            lines.append(f"| {k} | {o} | {n} |")
    else:
        lines.append("✅ 字节一致：默认配置回测报告在改动前后完全相同（排除时间戳类字段）。")
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"差异条数: {len(diffs)}")
    for k, o, n in diffs[:20]:
        print(f"  {k}: {o!r} -> {n!r}")
    print(f"报告: {out_md}")
    return 0 if not diffs else 2


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "run":
        sys.exit(run(sys.argv[2]))
    elif cmd == "diff":
        sys.exit(diff(sys.argv[2], sys.argv[3]))
    else:
        print(__doc__)
        sys.exit(64)
