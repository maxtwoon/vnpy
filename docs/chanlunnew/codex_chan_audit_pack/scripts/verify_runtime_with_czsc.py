#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行时验证脚本：需要 czsc。

默认不安装依赖；若加 --install，则执行 pip install --pre czsc==1.0.0rc8。
运行：
  python scripts/verify_runtime_with_czsc.py
  python scripts/verify_runtime_with_czsc.py --install
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "payload" / "chan_system_v1.0.2_extracted"
SRC = PKG / "src"
TEST = PKG / "tests" / "test_basic.py"
OUT_DIR = ROOT / "expected_outputs"
OUT_DIR.mkdir(exist_ok=True)


def run(cmd, cwd=None, check=False):
    print(f"\n$ {' '.join(map(str, cmd))}")
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    print(p.stdout)
    if p.stderr:
        print("[stderr]")
        print(p.stderr)
    if check and p.returncode != 0:
        raise SystemExit(p.returncode)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="install czsc==1.0.0rc8 before running")
    args = ap.parse_args()

    if args.install:
        run([sys.executable, "-m", "pip", "install", "--upgrade", "--pre", "czsc==1.0.0rc8"], check=True)

    try:
        import czsc
        from czsc import CZSC, Freq
        from czsc.mock import generate_symbol_kines
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"cannot import czsc: {e}", "hint": "rerun with --install or install czsc==1.0.0rc8 in a venv"}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    print(json.dumps({"czsc_version": getattr(czsc, "__version__", "unknown"), "czsc_file": getattr(czsc, "__file__", None)}, ensure_ascii=False, indent=2))

    # Run bundled tests
    env = os.environ.copy()
    p = run([sys.executable, str(TEST)], cwd=str(TEST.parent), check=False)
    test_ok = p.returncode == 0 and "7 passed, 0 failed" in p.stdout

    # API introspection
    df = generate_symbol_kines("000001", "30分钟", "20240101", "20240601")
    sys.path.insert(0, str(SRC))
    import czsc_adapter as A
    from bsp_state_machine import decide
    from dataclasses import asdict
    bars = A.df_to_rawbars(df, "000001", Freq.F30)
    cz = CZSC(bars)
    api_info = {
        "has_bars_raw": hasattr(cz, "bars_raw"),
        "has_bars_ubi": hasattr(cz, "bars_ubi"),
        "has_fx_list": hasattr(cz, "fx_list"),
        "has_bi_list": hasattr(cz, "bi_list"),
        "has_signals": hasattr(cz, "signals"),
        "has_zs_list": hasattr(cz, "zs_list"),
        "n_bi": len(getattr(cz, "bi_list", [])),
    }
    if getattr(cz, "bi_list", []):
        b0 = cz.bi_list[0]
        api_info.update({
            "bi_direction_type": type(b0.direction).__name__,
            "bi_direction_str": str(b0.direction),
            "bi_has_power_price": hasattr(b0, "power_price"),
            "bi_has_power_volume": hasattr(b0, "power_volume"),
        })

    result = A.analyze(df, "000001", Freq.F30, analysis_window=200, warmup_window=1000)
    signal = decide(result, "30分钟")
    runtime_info = {
        "test_basic_ok": test_ok,
        "test_returncode": p.returncode,
        "api_info": api_info,
        "adapter_top_keys": list(result.keys()),
        "meta": result.get("meta"),
        "n_bi_zs": len(result.get("bi_zs", [])),
        "xd": result.get("xd"),
        "xd_zs": result.get("xd_zs"),
        "has_new_bars_key": "new_bars" in result,
        "signal": asdict(signal),
    }
    (OUT_DIR / "runtime_report.json").write_text(json.dumps(runtime_info, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "sample_adapter_output.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[RUNTIME_REPORT]")
    print(json.dumps(runtime_info, ensure_ascii=False, indent=2))

    if not test_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
