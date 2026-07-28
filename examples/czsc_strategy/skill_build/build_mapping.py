"""
信号 ↔ 解盘话术 映射构建器
===========================

把"日线级客观缠论信号"与"真人解盘文本"按日期对齐，统计：
  - 在某个客观信号状态下，真人解盘高频使用哪些术语/措辞；
  - 各买卖点/结构形态在语料里的覆盖度；
  - 给 few-shot 选篇打分（形态多样性 + 情景树 + 背驰等）。

输入：
  - corpus.jsonl        （corpus_cleaner.py 产出）
  - sh000001_daily.csv  （fetch_sh_index_daily.py 产出）

输出：
  - mapping.json         机器可读：state -> 术语分布 + 样例日期
  - mapping.md           人读版映射表（供 SKILL.md / 术语表参考）
  - fewshot_candidates.json  few-shot 候选排序

口径：
  - 仅用训练区间（默认前 70%）做映射与选篇，后段留作评估，避免泄露。
  - 日线信号 as-of 当日：CZSC 用 bars[:当日] 增量计算，无未来函数。
  - 二买/二卖"确认"依赖锚点状态，本脚本只做信号层（候选级足够覆盖多数话术），
    锚点级映射留作后续用 ChanTimingStrategy 回放补充。

用法：
    python build_mapping.py --corpus corpus/corpus.jsonl --daily sh000001_daily.csv --out mapping
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from czsc import CZSC
from czsc import RawBar, Freq

try:
    # 与 diagnostics/signal_funnel.py 保持一致，优先用合并了买卖点的版本
    from chan_strategy.sell_signals import get_all_signals
except ImportError:  # pragma: no cover
    from chan_strategy.signals import get_legacy_signals as get_all_signals


# 关注的完全分类/买卖点信号后缀（用于映射的"状态"维度）
# 覆盖完整一二三买 + 一二三卖 + 数据状态 + 多空风控
_STATE_SUFFIXES = [
    "D1BI_方向V260615",
    "D1ZS_位置V260615",
    "D1ZS_数据状态V260615",
    "D1BI_背驰V260615",
    "D1ZS_结构状态V260615",
    "D1BSP_一买V260615",
    "D1BSP_二买V260615",
    "D1BSP_三买阶段V260615",
    "D1BSP_一卖V260615",
    "D1BSP_二卖V260615",
    "D1BSP_三卖阶段V260615",
    "D1BSP_风控V260615",
    "D1BSP_空头风控V260615",
]

_STATE_NAME_MAP = {
    "D1BI_方向V260615": "方向",
    "D1ZS_位置V260615": "中枢位置",
    "D1ZS_数据状态V260615": "数据状态",
    "D1BI_背驰V260615": "背驰",
    "D1ZS_结构状态V260615": "结构状态",
    "D1BSP_一买V260615": "一买",
    "D1BSP_二买V260615": "二买",
    "D1BSP_三买阶段V260615": "三买",
    "D1BSP_一卖V260615": "一卖",
    "D1BSP_二卖V260615": "二卖",
    "D1BSP_三卖阶段V260615": "三卖",
    "D1BSP_风控V260615": "多头风控",
    "D1BSP_空头风控V260615": "空头风控",
}

_TERM_PHRASES = {
    "第一种": {"role": "情景推演", "phrase": "第一种情景通常对应向上修复或突破延续，需要观察关键位能否站稳"},
    "第二种": {"role": "情景推演", "phrase": "第二种情景通常对应回落确认或结构降级，需要观察下沿是否失守"},
    "第三种": {"role": "情景推演", "phrase": "第三种情景通常对应中枢内反复震荡，等待方向重新选择"},
    "进入段": {"role": "结构解释", "phrase": "当前更像进入中枢后的再选择，不能简单按单边趋势处理"},
    "离开段": {"role": "结构解释", "phrase": "当前处在离开中枢后的力度观察阶段，重点看离开段是否有持续性"},
    "底分型": {"role": "结构解释", "phrase": "底分型出现后，短线修复仍需要后续笔确认"},
    "顶分型": {"role": "风险提醒", "phrase": "顶分型出现后，短线压力仍需要后续笔确认"},
    "盘整": {"role": "结构解释", "phrase": "盘整结构里更重视上下沿得失，而不是追逐单根K线"},
    "趋势": {"role": "结构解释", "phrase": "趋势延续需要新的离开段力度配合，否则容易回到中枢震荡"},
    "中枢构建": {"role": "结构解释", "phrase": "中枢构建阶段以震荡和边界确认优先"},
    "量能": {"role": "量能/板块人工确认", "phrase": "量能变化需要单独核验，若无量能配合则降低突破预期"},
    "线段": {"role": "结构解释", "phrase": "线段级别的延续或转折，需要结合下一笔确认"},
    "走势类型": {"role": "结构解释", "phrase": "走势类型尚需通过后续离开与回抽来确认级别"},
    "强调整": {"role": "风险提醒", "phrase": "强调整说明回落仍有承接，重点看是否守住关键下沿"},
    "承接": {"role": "风险提醒", "phrase": "承接是否有效，要看回落时能否守住中枢或前低区域"},
    "月线": {"role": "数据降级", "phrase": "更高级别背景只作方向约束，当前操作仍以本级别结构为准"},
    "30分钟": {"role": "数据降级", "phrase": "若有30分钟数据，应优先用其确认次级别节奏"},
    "5分钟": {"role": "数据降级", "phrase": "若有5分钟数据，应优先用其观察盘中回抽和离开力度"},
    "1分钟": {"role": "数据降级", "phrase": "1分钟结构只适合细化入场节奏，不替代日线结论"},
    "1F": {"role": "数据降级", "phrase": "1F结构只适合细化入场节奏，不替代日线结论"},
    "5F": {"role": "数据降级", "phrase": "5F结构用于观察短线承接和回抽质量"},
    "30F": {"role": "数据降级", "phrase": "30F结构用于连接日线判断与短线节奏"},
    "缺口": {"role": "量能/板块人工确认", "phrase": "缺口属于情绪与强弱辅助信号，需要结合是否回补判断"},
    "背驰": {"role": "风险提醒", "phrase": "背驰出现后不要急于下结论，重点观察确认笔和反向力度"},
    "分型": {"role": "结构解释", "phrase": "分型只是转折苗头，仍需后续笔确认"},
    "推演": {"role": "情景推演", "phrase": "当前更适合做情景推演，而不是给单一路径结论"},
    "日线": {"role": "数据降级", "phrase": "日线结构决定主要观察框架，次级别只负责细化节奏"},
    "温和": {"role": "风险提醒", "phrase": "走势相对温和时，边界得失比单日涨跌更重要"},
}


def _load_daily_bars(csv_path: Path, symbol: str = "sh000001") -> List[RawBar]:
    import pandas as pd
    df = pd.read_csv(csv_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    bars: List[RawBar] = []
    for i, row in df.iterrows():
        bars.append(RawBar(
            symbol=symbol, id=i, dt=row["datetime"].to_pydatetime(), freq=Freq.D,
            open=float(row["open"]), close=float(row["close"]),
            high=float(row["high"]), low=float(row["low"]),
            vol=float(row.get("volume", 0) or 0),
            amount=float(row.get("amount", 0) or 0),
        ))
    return bars


def _daily_signals_by_date(bars: List[RawBar], warmup: int = 30) -> Dict[str, dict]:
    """as-of 当日的日线信号字典，键为 'YYYY-MM-DD'。无未来函数。"""
    if len(bars) <= warmup:
        return {}
    czsc = CZSC(bars[:warmup])
    out: Dict[str, dict] = {}
    # 记录预热段最后一根
    for b in bars[warmup:]:
        czsc.update(b)
        sig = get_all_signals(czsc, "日线")
        out[b.dt.strftime("%Y-%m-%d")] = sig
    return out


def _state_of(sig: dict) -> Dict[str, str]:
    """从信号字典抽出我们关注的状态维度 -> v1。"""
    st: Dict[str, str] = {}
    for key, val in sig.items():
        for suf in _STATE_SUFFIXES:
            if key.endswith(suf):
                st[suf] = val.split("_")[0]
    return st


def _named_state_of(sig: dict) -> Dict[str, str]:
    return {_STATE_NAME_MAP.get(k, k): v for k, v in _state_of(sig).items()}


def _state_tags_for_date(sig_by_date: Dict[str, dict], date: str) -> Dict[str, str]:
    sig = sig_by_date.get(date) or {}
    return _named_state_of(sig)


def _is_active_state(value: str) -> bool:
    return bool(value) and not str(value).startswith("非") and value not in {"无", "不足", "未确认"}


def _build_narrative_templates(mapping_json: dict) -> List[dict]:
    """生成状态组合级句式。模板是客观结构到解盘表达的桥，不替代显著词统计。"""
    templates = [
        {
            "name": "上行在中枢上方",
            "conditions": {"方向": "向上", "中枢位置": "中枢上方"},
            "template": "当前方向向上且运行在中枢上方，结构偏强；后续重点观察离开段力度，以及能否持续站稳中枢上沿。",
        },
        {
            "name": "下行在中枢下方",
            "conditions": {"方向": "向下", "中枢位置": "中枢下方"},
            "template": "当前方向向下且处在中枢下方，调整压力仍在；若不能收回中枢下沿，弱势结构会继续延续。",
        },
        {
            "name": "中枢震荡",
            "conditions": {"中枢位置": "中枢内"},
            "template": "价格仍在中枢内部反复，方向选择尚未彻底完成；上沿与下沿分别是强弱切换的观察位。",
        },
        {
            "name": "方向向下但仍在中枢上方",
            "conditions": {"方向": "向下", "中枢位置": "中枢上方"},
            "template": "确认笔方向已经转弱，但价格仍在中枢上方，暂按高位震荡和回落观察处理；关键在于能否守住 ZG。",
        },
        {
            "name": "方向向上但仍在中枢下方",
            "conditions": {"方向": "向上", "中枢位置": "中枢下方"},
            "template": "确认笔方向有修复，但尚未有效收回中枢，属于弱修复结构；只有重新回到中枢内或站上 ZG，强度才会提高。",
        },
        {
            "name": "方向向上中枢内",
            "conditions": {"方向": "向上", "中枢位置": "中枢内"},
            "template": "方向向上但仍在中枢内部，属于中枢内偏强震荡；需要等待上沿突破来确认是否转为离开段。",
        },
        {
            "name": "确认偏弱但最新价修复",
            "conditions": {"中枢位置": "中枢下方", "预期态": "中枢上方"},
            "template": "确认结构仍偏弱，但最新收盘已经重新站到中枢上方，短线存在修复；后续重点看能否维持在 ZG 上方。",
        },
        {
            "name": "确认偏弱但最新价回中枢",
            "conditions": {"中枢位置": "中枢下方", "预期态": "中枢内"},
            "template": "确认结构仍在中枢下方，但最新收盘已经回到中枢内部，弱势有所缓和；接下来观察能否继续向上挑战 ZG。",
        },
        {
            "name": "确认偏强但最新价回落",
            "conditions": {"中枢位置": "中枢上方", "预期态": "中枢内"},
            "template": "确认结构仍偏强，但最新收盘已经回到中枢内部，说明上方延续力度不足；后续重点看能否重新收回 ZG。",
        },
        {
            "name": "强势延续无背驰",
            "conditions": {"中枢位置": "中枢上方", "预期态": "中枢上方", "背驰": "无"},
            "template": "确认结构和最新收盘都在中枢上方，且暂未出现背驰，属于偏强延续；后续重点观察离开段力度是否继续放大。",
        },
        {
            "name": "确认偏强但最新价失守",
            "conditions": {"中枢位置": "中枢上方", "预期态": "中枢下方"},
            "template": "确认结构仍显示在中枢上方，但最新收盘已经跌到中枢下方，短线有结构转弱风险；需要优先观察 ZD 能否收回。",
        },
        {
            "name": "确认震荡贴近上沿",
            "conditions": {"中枢位置": "中枢内", "预期态边界": "ZG"},
            "template": "确认结构处在中枢震荡，最新价更接近上沿；若继续站上 ZG，才有向上离开中枢的条件。",
        },
        {
            "name": "确认震荡贴近下沿",
            "conditions": {"中枢位置": "中枢内", "预期态边界": "ZD"},
            "template": "确认结构处在中枢震荡，最新价更接近下沿；若跌破 ZD，调整压力会明显加大。",
        },
        {
            "name": "疑似背驰",
            "conditions": {"背驰": "疑似"},
            "template": "结构上已出现背驰苗头，不宜简单追随单边；下一段力度是否衰减，是确认转折质量的关键。",
        },
        {
            "name": "三买确认",
            "conditions": {"三买": "三买确认"},
            "template": "三买确认意味着回抽未破原中枢上沿，属于偏强延续结构；若后续放量上攻，趋势延伸概率提高。",
        },
        {
            "name": "三买观察",
            "conditions": {"三买": "回抽不入中枢"},
            "template": "三买处在观察阶段，回抽暂未进入中枢；需要等待确认笔或后续上攻来验证承接力度。",
        },
        {
            "name": "三卖确认",
            "conditions": {"三卖": "三卖确认"},
            "template": "三卖确认意味着反抽未回到原中枢下沿之上，结构偏弱；后续若继续下行，调整级别可能扩大。",
        },
        {
            "name": "三卖观察",
            "conditions": {"三卖": "反抽不入中枢"},
            "template": "三卖处在观察阶段，反抽暂未进入中枢；需要等待确认笔或再次下破来验证空方力度。",
        },
        {
            "name": "多头结构失效",
            "conditions": {"多头风控": "止损触发"},
            "template": "多头结构已经触发失效条件，应优先降低多头预期，等待新的中枢或买点重新形成。",
        },
        {
            "name": "空头结构失效",
            "conditions": {"空头风控": "止损触发"},
            "template": "空头结构已经触发失效条件，应优先降低空头预期，等待新的中枢或卖点重新形成。",
        },
    ]

    # 只保留当前信号枚举实际出现过的信号条件；预期态条件由 analyzer 运行时提供。
    named_values = defaultdict(set)
    for dim, vals in mapping_json.items():
        name = _STATE_NAME_MAP.get(dim, dim)
        named_values[name].update(vals.keys())
    kept = []
    for item in templates:
        if all(
            key.startswith("预期态") or value in named_values.get(key, {value})
            for key, value in item["conditions"].items()
        ):
            kept.append(item)
    return kept


def _fewshot_score(rec: dict) -> float:
    """few-shot 选篇打分：覆盖的买卖点种类 + 是否含背驰 + 情景树分支 + 适中长度。"""
    th = rec.get("term_hits", {})
    bsp = th.get("买卖点", {})
    structure = th.get("结构", {})
    score = 0.0
    score += 2.0 * len(bsp)                       # 覆盖的买卖点种类越多越好
    score += 1.5 if "背驰" in structure else 0
    score += min(rec.get("n_scenarios", 0), 3)    # 情景树分支（封顶 3）
    score += 1.0 if structure.get("中枢") else 0
    # 长度适中（太短信息少、太长难做范例）
    n = rec.get("char_len", 0)
    score += 1.0 if 300 <= n <= 1500 else 0
    return score


def _fewshot_categories(rec: dict) -> list:
    th = rec.get("term_hits", {})
    terms = set(th.get("买卖点", {}).keys()) | set(th.get("结构", {}).keys())
    cats = []
    for cat in ["一买", "二买", "三买", "一卖", "二卖", "三卖", "背驰", "趋势", "盘整"]:
        if cat in terms:
            cats.append(cat)
    if not cats:
        cats.append("综合结构")
    return cats


def _active_mapping_gaps(mapping_json: dict) -> list[dict]:
    gaps = []
    suffix_by_name = {v: k for k, v in _STATE_NAME_MAP.items()}
    for name in ["一买", "二买", "三买", "一卖", "二卖", "三卖"]:
        dim = suffix_by_name[name]
        vals = mapping_json.get(dim, {})
        active_vals = [v for v in vals if _is_active_state(v)]
        active_with_words = []
        for val in active_vals:
            rows = vals[val].get("top_by_lift", [])
            if any(r["lift"] > 1 for r in rows):
                active_with_words.append(val)
        if not active_vals:
            gaps.append({
                "type": "state_absent",
                "dimension": name,
                "message": f"{name} 在日线训练集未出现有效候选/确认状态，无法挖掘对应话术。",
            })
        elif not active_with_words:
            gaps.append({
                "type": "no_significant_words",
                "dimension": name,
                "active_states": active_vals,
                "message": f"{name} 在日线训练集中有状态 {active_vals}，但无达到支持度和 lift 的显著话术。",
            })
    return gaps


def main():
    ap = argparse.ArgumentParser(description="信号↔解盘话术 映射构建器")
    ap.add_argument("--corpus", default="corpus/corpus.jsonl")
    ap.add_argument("--daily", default="sh000001_daily.csv")
    ap.add_argument("--out", default="mapping")
    ap.add_argument("--symbol", default="sh000001")
    ap.add_argument("--train-frac", type=float, default=0.70,
                    help="训练区间占比，其余留作评估（按时间切，不随机）")
    ap.add_argument("--warmup", type=int, default=30, help="日线预热根数")
    ap.add_argument("--min-support", type=int, default=3,
                    help="术语在某状态下至少出现的天数，低于则不计入显著词")
    ap.add_argument("--lift-top", type=int, default=12, help="每状态保留的 lift 显著词数")
    _ref = Path(__file__).resolve().parent / "reference"
    ap.add_argument("--narrative-out", default=str(_ref / "signal_to_narrative.md"),
                    help="同步写入的话术映射资源（skill 直接读取）")
    ap.add_argument("--export-fewshot", type=int, default=0,
                    help="导出 TopN few-shot 候选正文到 --fewshot-out（0=不导出）")
    ap.add_argument("--fewshot-out", default=str(_ref / "few_shot" / "auto"),
                    help="few-shot 自动导出目录（待人工确认后移入 few_shot/）")
    args = ap.parse_args()

    if not (0.0 < args.train_frac < 1.0):
        ap.error(f"--train-frac 必须在 (0,1) 开区间，收到 {args.train_frac}；"
                 f"=1 会无评估集，=0 会训练集为空")

    corpus_path = Path(args.corpus)
    daily_path = Path(args.daily)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if not corpus_path.exists():
        print(f"找不到语料: {corpus_path}（先跑 corpus_cleaner.py）"); sys.exit(1)
    if not daily_path.exists():
        print(f"找不到日线: {daily_path}（先跑 fetch_sh_index_daily.py）"); sys.exit(1)

    # 读语料（每篇一行）
    records = [json.loads(ln) for ln in corpus_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    records.sort(key=lambda r: (r["date"], r.get("article_idx", 0)))

    # 时间切分：训练区间
    dates_sorted = sorted({r["date"] for r in records})
    cut = dates_sorted[int(len(dates_sorted) * args.train_frac)] if dates_sorted else None
    train_records = [r for r in records if r["date"] < cut] if cut else records
    narrative_train_records = [
        r for r in train_records
        if r.get("article_type", "market_review") in {"market_review", "mixed"}
    ]
    print(
        f"语料 {len(records)} 篇，训练区间 {len(train_records)} 篇 (< {cut})，"
        f"用于映射/范例 {len(narrative_train_records)} 篇"
    )

    # 日线信号
    bars = _load_daily_bars(daily_path, args.symbol)
    sig_by_date = _daily_signals_by_date(bars, warmup=args.warmup)
    print(f"日线信号 as-of 覆盖 {len(sig_by_date)} 个交易日")

    # ---- 对齐：先按日期聚合术语（同日多篇合并），每个交易日只计一次 ----
    terms_by_date: Dict[str, set] = defaultdict(set)
    for r in narrative_train_records:
        for grp in r.get("term_hits", {}).values():
            terms_by_date[r["date"]].update(grp.keys())
    aligned_days = []
    for d in sorted(terms_by_date):
        if d not in sig_by_date:
            continue
        aligned_days.append((d, _state_of(sig_by_date[d]), terms_by_date[d]))

    total_days = len(aligned_days)
    print(f"成功对齐(语料∩日线信号) {total_days} 天")
    if total_days == 0:
        print("无对齐天，检查日期格式/区间是否相交"); return

    # 基线：每个术语在全部对齐天里的出现天数（presence）
    baseline = Counter()
    for _, _, terms in aligned_days:
        baseline.update(terms)

    # 每个状态维度/取值：天数 + 术语 presence
    state_days: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    state_term: Dict[str, Dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    examples: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    for d, state, terms in aligned_days:
        for dim, val in state.items():
            state_days[dim][val] += 1
            for t in terms:
                state_term[dim][val][t] += 1
            if len(examples[dim][val]) < 5:
                examples[dim][val].append(d)

    def _lift_rows(dim: str, val: str):
        nd = state_days[dim][val]
        rows = []
        for t, c in state_term[dim][val].items():
            if c < args.min_support:
                continue
            state_rate = c / nd
            base_rate = baseline[t] / total_days
            lift = state_rate / base_rate if base_rate > 0 else 0.0
            rows.append({
                "term": t, "days": c,
                "state_rate": round(state_rate, 3),
                "base_rate": round(base_rate, 3),
                "lift": round(lift, 2),
            })
        # 按 lift 降序，lift 同分看 days
        rows.sort(key=lambda x: (-x["lift"], -x["days"]))
        return rows[:args.lift_top]

    # ---- mapping.json：以 lift 显著词为主，附原始计数 ----
    mapping_json = {}
    for dim, vals in state_days.items():
        mapping_json[dim] = {}
        for val, nd in vals.items():
            mapping_json[dim][val] = {
                "n_days": nd,
                "top_by_lift": _lift_rows(dim, val),
                "top_by_count": dict(state_term[dim][val].most_common(10)),
                "example_dates": examples[dim][val],
            }
    (out / "mapping.json").write_text(
        json.dumps(mapping_json, ensure_ascii=False, indent=2), encoding="utf-8")
    narrative_templates = _build_narrative_templates(mapping_json)
    (out / "narrative_templates.json").write_text(
        json.dumps(narrative_templates, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "term_phrases.json").write_text(
        json.dumps(_TERM_PHRASES, ensure_ascii=False, indent=2), encoding="utf-8")
    mapping_gaps = _active_mapping_gaps(mapping_json)
    (out / "mapping_gaps.json").write_text(
        json.dumps(mapping_gaps, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- mapping.md（人读，展示 lift 显著词）----
    md = ["# 信号 → 解盘话术 映射表", "",
          f"> 训练区间: {dates_sorted[0]} ~ {cut}  对齐天数: {total_days}",
          f"> 显著词 = 相对全语料基线出现率更高的术语 (lift>1)，min_support={args.min_support}", ""]
    for dim, vals in mapping_json.items():
        md.append(f"## {dim}")
        md.append("")
        for val, info in sorted(vals.items(), key=lambda x: -x[1]["n_days"]):
            md.append(f"### {val}  (n={info['n_days']}天)")
            if info["top_by_lift"]:
                for row in info["top_by_lift"]:
                    md.append(f"- {row['term']}  lift={row['lift']} "
                              f"(状态内{row['state_rate']:.0%} vs 基线{row['base_rate']:.0%}, {row['days']}天)")
            else:
                md.append("- （无达到支持度的显著词）")
            md.append(f"- 样例日: {', '.join(info['example_dates'])}")
            md.append("")
    (out / "mapping.md").write_text("\n".join(md), encoding="utf-8")

    # ---- 同步写入 skill 资源 reference/signal_to_narrative.md（lift>1 显著词）----
    nar = ["# 信号 → 解盘话术（由 build_mapping.py 自动生成）", "",
           f"> 训练区间 {dates_sorted[0]} ~ {cut}，对齐 {total_days} 天；仅保留 lift>1 显著词。",
           "> 本文件由脚本覆盖，请勿手改；需调整改 build_mapping.py。", "",
           "## 组合句式模板",
           "> 先按条件匹配组合模板，再用下方显著词补充语言风格。", ""]
    for item in narrative_templates:
        cond = " & ".join(f"{k}={v}" for k, v in item["conditions"].items())
        nar.append(f"- 条件: {cond} → {item['template']}")
    nar.append("")
    nar.append("## 术语短句素材")
    nar.append("> 显著词只作为风格线索，实际写作优先使用这些短句素材。")
    nar.append("")
    for term, meta in sorted(_TERM_PHRASES.items()):
        nar.append(f"- {term} [{meta['role']}] → {meta['phrase']}")
    nar.append("")
    nar.append("## 状态显著词")
    nar.append("")
    for dim, vals in mapping_json.items():
        nar.append(f"### {_STATE_NAME_MAP.get(dim, dim)}")
        emitted = False
        for val, info in sorted(vals.items(), key=lambda x: -x[1]["n_days"]):
            words = [r["term"] for r in info["top_by_lift"] if r["lift"] > 1][:8]
            if words:
                emitted = True
                nar.append(f"- {val} → " + "、".join(words))
        if not emitted:
            nar.append("- （语料缺口：该维度在日线训练集缺少可用显著话术）")
        nar.append("")
    nar.append("## 语料缺口")
    nar.append("")
    if mapping_gaps:
        for gap in mapping_gaps:
            nar.append(f"- {gap['dimension']}: {gap['message']}")
    else:
        nar.append("- 未发现买卖点主动状态的话术缺口。")
    nar.append("")
    narrative_path = Path(args.narrative_out)
    narrative_path.parent.mkdir(parents=True, exist_ok=True)
    narrative_path.write_text("\n".join(nar), encoding="utf-8")

    # ---- 写出 train/eval split，供 held-out 评估 ----
    eval_records = [r for r in records if cut and r["date"] >= cut]
    with (out / "eval_records.jsonl").open("w", encoding="utf-8") as fh:
        for r in eval_records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    split_meta = {
        "train_frac": args.train_frac,
        "cut_date": cut,
        "n_total_articles": len(records),
        "n_train_articles": len(train_records),
        "n_eval_articles": len(eval_records),
        "train_range": [dates_sorted[0], cut] if dates_sorted else None,
        "eval_range": [cut, dates_sorted[-1]] if dates_sorted else None,
        "aligned_train_days": total_days,
    }
    (out / "split_meta.json").write_text(
        json.dumps(split_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- few-shot 候选排序（仅训练区间）----
    scored = sorted(
        ({"date": r["date"], "article_idx": r.get("article_idx", 1),
          "title": r.get("article_title", ""),
          "score": round(_fewshot_score(r), 2),
          "n_scenarios": r.get("n_scenarios", 0),
          "buy_sell_terms": list(r.get("term_hits", {}).get("买卖点", {}).keys()),
          "char_len": r.get("char_len", 0),
          "state_tags": _state_tags_for_date(sig_by_date, r["date"])}
         for r in narrative_train_records),
        key=lambda x: -x["score"],
    )
    (out / "fewshot_candidates.json").write_text(
        json.dumps(scored[:40], ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 可选：自动导出 TopN few-shot 正文（待人工确认后移入 reference/few_shot/）----
    if args.export_fewshot > 0:
        rec_by_key = {(r["date"], r.get("article_idx", 1)): r for r in train_records}
        fs_dir = Path(args.fewshot_out)
        fs_dir.mkdir(parents=True, exist_ok=True)
        for stale in list(fs_dir.glob("*.md")) + list(fs_dir.glob("*.json")):
            stale.unlink()
        manifest = []
        desired = ["一买", "二买", "三买", "一卖", "二卖", "三卖", "背驰", "趋势", "盘整"]
        export_scored = list(scored)
        by_category = {cat: [] for cat in desired + ["综合结构"]}
        for s in export_scored:
            rec = rec_by_key.get((s["date"], s["article_idx"]))
            if not rec:
                continue
            for cat in _fewshot_categories(rec):
                by_category.setdefault(cat, []).append(s)
        selected = []
        used_keys = set()
        for cat in desired:
            for s in by_category.get(cat, []):
                key = (s["date"], s["article_idx"])
                if key not in used_keys:
                    selected.append((cat, s))
                    used_keys.add(key)
                    break
        for cat in desired + ["综合结构"]:
            for s in by_category.get(cat, []):
                if len(selected) >= args.export_fewshot:
                    break
                key = (s["date"], s["article_idx"])
                if key not in used_keys:
                    selected.append((cat, s))
                    used_keys.add(key)
            if len(selected) >= args.export_fewshot:
                break
        fewshot_gaps = [
            cat for cat in desired
            if not any(selected_cat == cat for selected_cat, _ in selected)
        ]
        (fs_dir / "fewshot_gaps.json").write_text(
            json.dumps(fewshot_gaps, ensure_ascii=False, indent=2), encoding="utf-8")
        for cat, s in selected[:args.export_fewshot]:
            rec = rec_by_key.get((s["date"], s["article_idx"]))
            if not rec:
                continue
            tag = "_".join(s["buy_sell_terms"][:2]) or cat
            fname = f"{s['date']}_{tag}.md"
            (fs_dir / fname).write_text(
                f"# {s['date']} {rec.get('article_title','')}\n"
                f"> 自动导出 few-shot 候选 (score={s['score']}, 情景={s['n_scenarios']}, "
                f"买卖点={s['buy_sell_terms']}, category={cat})\n> 待人工确认后移入 reference/few_shot/\n\n"
                f"{rec.get('text','')}\n",
                encoding="utf-8")
            manifest.append({"file": fname, "category": cat, **s})
        (fs_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if fewshot_gaps:
            print(f"  few-shot 形态缺口: {fewshot_gaps}")
        print(f"  已导出 {len(manifest)} 篇 few-shot 候选到 {fs_dir}")

    print(f"\n输出:")
    print(f"  {out/'mapping.json'}")
    print(f"  {out/'mapping_gaps.json'}  (话术缺口)")
    print(f"  {out/'narrative_templates.json'}  (组合句式模板)")
    print(f"  {out/'mapping.md'}   (lift 显著词)")
    print(f"  {narrative_path}   (已同步到 skill 资源)")
    print(f"  {out/'fewshot_candidates.json'}  (Top40 候选)")
    print(f"  {out/'eval_records.jsonl'}  ({len(eval_records)} 篇留出评估)")
    print(f"  {out/'split_meta.json'}")
    print("\nfew-shot Top10 候选:")
    for s in scored[:10]:
        print(f"  {s['date']} 分{s['score']} 情景{s['n_scenarios']} 买卖点{s['buy_sell_terms']} 《{s['title']}》")


if __name__ == "__main__":
    main()
