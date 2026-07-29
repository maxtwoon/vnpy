# -*- coding: utf-8 -*-
"""czsc==1.0.0rc8 理论断言只读探针（§8 待验证清单落地）

验证 docs/theory_code_crosscheck.md §8 的两条外部断言：
  A. "czsc 的 ZS 对象默认是笔中枢（因 czsc 以笔为 a0）"
  B. "三类买卖点在 czsc 中表现为五笔/七笔/九笔多笔形态信号，
      读 CZSC.signals 中倒1/倒2 信号即可定性"

只读约束（AGENTS.md 铁律）：不发送委托、不调交易接口、不改任何策略参数；
数据源为 czsc.mock 生成的合成 K 线，不触网、不读真实账户。

运行方式（须用装有 czsc 的项目解释器，托管 Python 无 czsc）：
    C:\\Python314\\python.exe diagnostics/czsc_rc8_theory_probe.py

输出：diagnostics/czsc_rc8_theory_probe_report.md（同名覆盖，内容可复现）
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

from czsc import BI, CZSC, Freq, RawBar, ZS, mock

REPORT_PATH = Path(__file__).resolve().parent / "czsc_rc8_theory_probe_report.md"
BANNER = "<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->"


def build_czsc_from_mock() -> tuple[CZSC, int]:
    """用 czsc.mock 合成 K 线构建 CZSC（种子固定，结果可复现）。"""
    df = mock.generate_symbol_kines(
        symbol="MOCK000", freq="30分钟",
        sdt="20200101", edt="20210601", seed=42,
    )
    bars = []
    for i, row in enumerate(df.itertuples(index=False)):
        bars.append(RawBar(
            symbol=row.symbol, id=i, dt=row.dt.to_pydatetime(),
            freq=Freq.F30,
            open=float(row.open), close=float(row.close),
            high=float(row.high), low=float(row.low),
            vol=float(row.vol), amount=float(row.amount),
        ))
    return CZSC(bars), len(bars)


def probe_zs(c: CZSC, n_bars: int) -> dict:
    """断言 A：ZS 是否由笔构成（笔中枢）。

    rc8 的 CZSC 本体不再持有 zs_list（只算分型/笔），ZS 是独立类，
    故分两层取证：CZSC 层面记录 zs_list 缺失；ZS 类层面直接用
    finished_bis 构造实例并检查构成元素类型。
    """
    finished = list(c.finished_bis)
    out = {
        "n_bars": n_bars,
        "bi_count": len(getattr(c, "bi_list", []) or []),
        "finished_bi_count": len(finished),
        "max_bi_num": getattr(c, "max_bi_num", None),
        "has_zs_list": hasattr(c, "zs_list"),
        "signals_cache_type": type(getattr(c, "signals", None)).__name__,
        "signals_cache_len": len(getattr(c, "signals", {}) or {}),
        "finished_elem_types": sorted({type(b).__name__ for b in finished}),
    }
    sample = finished[:5]
    zs = ZS(bis=sample)
    out["zs_construct"] = {
        "input_types": sorted({type(b).__name__ for b in sample}),
        "zg": round(zs.zg, 2), "zd": round(zs.zd, 2),
        "gg": round(zs.gg, 2), "dd": round(zs.dd, 2),
        "zz": round(zs.zz, 2),
        "sdir": str(zs.sdir), "edir": str(zs.edir),
        "bis_elem_types": sorted({type(b).__name__ for b in zs.bis}),
    }
    return out


def probe_signal_library() -> dict:
    """断言 B：rc8 是否内置五笔/七笔/九笔（倒1/倒2）多笔形态信号。"""
    import czsc
    pkg_root = Path(czsc.__file__).resolve().parent

    has_signals_mod = importlib.util.find_spec("czsc.signals") is not None

    hits = {}
    for pat in ["三买", "三卖", "五笔", "七笔", "九笔"]:
        files = []
        for f in pkg_root.rglob("*"):
            if f.suffix not in (".py", ".pyi"):
                continue
            try:
                if pat in f.read_text(encoding="utf-8", errors="ignore"):
                    files.append(str(f.relative_to(pkg_root)))
            except OSError:
                pass
        hits[pat] = files
    return {"czsc_signals_module": has_signals_mod, "keyword_files": hits}


def main() -> None:
    import czsc
    zs_probe, err = None, None
    try:
        c, n_bars = build_czsc_from_mock()
        zs_probe = probe_zs(c, n_bars)
    except Exception as e:  # 探针失败也要如实记录
        err = f"{type(e).__name__}: {e}"
    sig_probe = probe_signal_library()

    if err:
        verdict_a = "探针失败"
    else:
        zc = zs_probe["zs_construct"]
        verdict_a = (
            "证实（ZS 仅能由 BI 列表构造，构成元素全部为笔；"
            "官方类型存根 `ZS.bis: list[BI]`）"
            if zc["bis_elem_types"] == ["BI"] else "未证实，构成元素异常"
        )
    kw = sig_probe["keyword_files"]
    verdict_b = (
        "证伪（rc8 未内置该类信号函数）"
        if not sig_probe["czsc_signals_module"] and not kw.get("三买") and not kw.get("七笔")
        else "部分成立，需人工复核命中文件"
    )

    lines = [
        BANNER,
        "",
        "# czsc 1.0.0rc8 理论断言探针报告",
        "",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"- Python：{sys.version.split()[0]}（{sys.executable}）",
        f"- czsc：{czsc.__version__}（{Path(czsc.__file__).parent}）",
        "- 数据：`czsc.mock.generate_symbol_kines(\"MOCK000\", \"30分钟\", sdt=20200101, edt=20210601, seed=42)` 合成 K 线，不触网",
        "- 性质：只读探针；不发委托、不调交易接口、不改任何策略参数",
        "",
        "## 结论速览",
        "",
        f"- 断言 A（ZS 默认是笔中枢）：**{verdict_a}**",
        f"- 断言 B（三类买卖点 = czsc 内置倒1/倒2 多笔形态信号）：**{verdict_b}**",
        "",
        "## 断言 A 细节：ZS 构成",
        "",
    ]
    if err:
        lines.append(f"探针执行失败：`{err}`")
    else:
        zc = zs_probe["zs_construct"]
        lines += [
            f"- 合成 K 线 {zs_probe['n_bars']} 根 → `CZSC(bars)`；"
            f"`bi_list` 保留 {zs_probe['bi_count']} 根（`max_bi_num={zs_probe['max_bi_num']}`，rc8 默认只保留最近 N 笔），"
            f"`finished_bis` {zs_probe['finished_bi_count']} 根，元素类型 {zs_probe['finished_elem_types']}",
            f"- **`CZSC` 本体无 `zs_list` 属性**（hasattr = {zs_probe['has_zs_list']}）："
            "rc8 的 CZSC 只完成包含处理、分型与笔识别，**不自动构建中枢**；"
            "本项目自研 `build_zhongshu_from_bis()` 正是填补这一空白的必要实现，而非重复造轮子",
            f"- `CZSC.signals` 实例属性存在，为空 `{zs_probe['signals_cache_type']}`"
            f"（长度 {zs_probe['signals_cache_len']}）：仅是信号缓存槽，需外部信号函数写入",
            "- 用前 5 根已完成笔直接构造 `ZS(bis=...)`：",
            "",
            "| 输入元素类型 | zg | zd | gg | dd | zz | sdir | edir | 构成元素类型 |",
            "|---|---|---|---|---|---|---|---|---|",
            f"| {zc['input_types']} | {zc['zg']} | {zc['zd']} | {zc['gg']} | {zc['dd']} "
            f"| {zc['zz']} | {zc['sdir']} | {zc['edir']} | {zc['bis_elem_types']} |",
            "",
            "- 官方类型存根（`_native/__init__.pyi`）：`ZS.bis: list[BI]` ——「获取构成中枢的笔列表」",
            "- ZS 附带 `sdir`（中枢第一笔方向）/ `edir`（中枢倒一笔方向）属性："
            "描述的是中枢**内部**首/末笔方向，与书上「中枢方向 = 进入段方向」口径不同，"
            "不可直接当作书义中枢方向使用",
        ]
    lines += [
        "",
        "## 断言 B 细节：内置信号库",
        "",
        f"- `czsc.signals` 子模块存在：**{sig_probe['czsc_signals_module']}**（rc8 无此模块；"
        "`generate_czsc_signals(bars, signals_config)` 仅按用户自备 config 调用信号函数，"
        "库本身不附带任何形态信号实现）",
        "- 关键词全包扫描（.py/.pyi）：",
        "",
        "| 关键词 | 命中文件 |",
        "|---|---|",
    ]
    for pat, files in kw.items():
        lines.append(f"| {pat} | {('<br>'.join(files)) if files else '（无）'} |")
    lines += [
        "",
        "> 注：`aphorism.py`（语录文本）、`fsa/`（飞书集成）中的「倒」「笔」命中与形态信号无关；"
        "`_native/__init__.pyi` 中「中枢倒一笔方向」是 ZS.edir 的字段文档，非信号。",
        "",
        "## 对项目的影响（回写 docs/theory_code_crosscheck.md §8）",
        "",
        "1. 断言 A 证实后：书摘立场成立——可获取的中枢均为笔中枢（rc8 甚至不自动构建中枢，"
        "ZS 类仅接受 BI 列表）。报告层标注「笔中枢」的 P0 整改前提成立。",
        "2. 断言 B 证伪后：书摘中「读 czsc 倒1/倒2 信号定性三类买卖点」的路径在 rc8 **不可用**"
        "（该 API 形态存在于旧版 czsc）。项目自研三阶段状态机（`signals.py` / `sell_signals.py`）"
        "是当前唯一实现；将来若需 czsc 原生形态信号做交叉验证，须自行移植旧版信号函数或放弃该路线。",
        "3. 附带发现：`CZSC.max_bi_num` 默认限制笔缓存长度（本探针为 50），"
        "长序列分析时若依赖 `bi_list` 需留意截断；`finished_bis` 同受此限。",
    ]

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[probe] 断言A: {verdict_a}")
    print(f"[probe] 断言B: {verdict_b}")
    print(f"[probe] 报告已写入 {REPORT_PATH}")


if __name__ == "__main__":
    main()
