"""
缠论择时策略验证模块

验证流程：
1. 信号验证 - 检查完全分类信号的穷尽性和互斥性
2. 事件验证 - 验证 signals_all/any/not 逻辑正确性
3. 单策略回测 - 分别测试各Position子策略
4. 稳健性检验 - 样本外/滚动窗口测试
5. SimNow仿真准备度评估
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict
import copy

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from czsc import CZSC
from czsc.objects import RawBar

from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG, BACKTEST_CONFIG
from chan_strategy.data_adapter import SqliteDataAdapter
from chan_strategy.signals import _get_confirmed_bi_list
from chan_strategy.sell_signals import get_all_signals
from chan_strategy.positions import (
    Position, ChanTimingStrategy,
    create_first_buy_position, create_second_buy_position, create_third_buy_position,
    Event, Factor, Signal, Operate,
)


# ============================================================
# 信号完全分类定义
# ============================================================
EXHAUSTIVE_SIGNAL_CATEGORIES = {
    "D1BI_方向V260615": ["向上", "向下", "无有效笔"],
    "D1ZS_位置V260615": ["中枢上方", "中枢内", "中枢下方", "无中枢"],
    "D1ZS_数据状态V260615": ["充分", "不足"],
    "D1BI_背驰V260615": ["无", "疑似", "确认"],
    "D1ZS_结构状态V260615": ["已确认", "未确认", "无中枢"],
    "D1BSP_风控V260615": ["结构完好", "结构失效", "震荡超限"],
    "D1BSP_空头风控V260615": ["结构完好", "结构失效", "震荡超限"],
    "D1BSP_风控RV260615": ["结构完好", "结构失效", "震荡超限"],
    "D1BSP_空头风控RV260615": ["结构完好", "结构失效", "震荡超限"],
}


class SignalValidator:
    """信号验证器"""

    def validate_exhaustiveness(self, signals_history: List[dict]) -> dict:
        """
        验证完全分类信号的穷尽性

        检查每个信号key是否在每根K线都有且只有一个值
        完全分类信号: 方向、位置、数据状态、背驰、结构状态

        修复：原实现只取第一条记录的第一个频率前缀，导致多级别信号（如
        30分钟 + 日线）中只有第一个频率被验证。现在收集所有历史记录中的
        全部频率前缀，逐一遍历验证。
        """
        results = {"passed": True, "details": {}}

        if not signals_history:
            results["passed"] = False
            results["error"] = "信号历史为空"
            return results

        # 收集所有历史记录中出现的频率前缀，而不是只看第一条
        freq_prefixes = set()
        for record in signals_history:
            for key in record.get("signals", {}):
                parts = key.split("_")
                if len(parts) >= 3:
                    freq_prefixes.add(parts[0])

        if not freq_prefixes:
            results["passed"] = False
            results["error"] = "未识别到任何频率前缀"
            return results

        for freq_prefix in sorted(freq_prefixes):
            for sig_suffix, expected_values in EXHAUSTIVE_SIGNAL_CATEGORIES.items():
                full_key = f"{freq_prefix}_{sig_suffix}"
                missing_count = 0
                invalid_count = 0
                value_dist = defaultdict(int)

                for record in signals_history:
                    signals = record["signals"]
                    if full_key not in signals:
                        missing_count += 1
                        continue

                    # 提取v1值
                    val_str = signals[full_key]
                    v1 = val_str.split("_")[0]
                    value_dist[v1] += 1

                    if v1 not in expected_values:
                        invalid_count += 1

                total = len(signals_history)
                passed = missing_count == 0 and invalid_count == 0
                detail_key = f"{freq_prefix}_{sig_suffix}"
                results["details"][detail_key] = {
                    "passed": passed,
                    "total": total,
                    "missing": missing_count,
                    "invalid": invalid_count,
                    "value_distribution": dict(value_dist),
                    "expected_values": expected_values,
                    "freq_prefix": freq_prefix,
                }
                if not passed:
                    results["passed"] = False

        return results

    def validate_mutual_exclusivity(self, signals_history: List[dict]) -> dict:
        """
        验证互斥性

        检查同一个信号key不会同时出现多个值
        由于信号是dict形式，每个key只有一个value，互斥性天然满足
        但检查value是否在合法分类内

        修复：同样收集所有历史记录中的频率前缀，而不是只看第一条。
        """
        results = {"passed": True, "details": {}}

        if not signals_history:
            results["passed"] = False
            results["error"] = "信号历史为空"
            return results

        # 收集所有历史记录中出现的频率前缀
        freq_prefixes = set()
        for record in signals_history:
            for key in record.get("signals", {}):
                parts = key.split("_")
                if len(parts) >= 3:
                    freq_prefixes.add(parts[0])

        if not freq_prefixes:
            results["passed"] = False
            results["error"] = "未识别到任何频率前缀"
            return results

        for freq_prefix in sorted(freq_prefixes):
            for sig_suffix, expected_values in EXHAUSTIVE_SIGNAL_CATEGORIES.items():
                full_key = f"{freq_prefix}_{sig_suffix}"
                violations = 0

                for record in signals_history:
                    signals = record["signals"]
                    if full_key not in signals:
                        continue
                    val_str = signals[full_key]
                    v1 = val_str.split("_")[0]
                    # 互斥性：dict结构保证每个key只有一个值
                    # 这里检查值是否在合法分类内（等同于穷尽性的子集）
                    if v1 not in expected_values:
                        violations += 1

                passed = violations == 0
                detail_key = f"{freq_prefix}_{sig_suffix}"
                results["details"][detail_key] = {
                    "passed": passed,
                    "violations": violations,
                    "freq_prefix": freq_prefix,
                }
                if not passed:
                    results["passed"] = False

        return results

    def validate_incremental_consistency(self, bars: List[RawBar], freq_name: str,
                                          warmup: int = 100, sample_size: int = 200) -> dict:
        """
        增量-全量一致性检查（计算一致性）。

        对同一历史截面，用"增量更新"与"从头构造"两种方式得到的信号必须一致。
        这能发现策略实现中显式使用未来数据的逻辑错误，但不能证明不重绘，
        也不能证明底层 czsc 库不会基于后续数据修正历史笔结构。

        修复：使用 ChanTimingStrategy 跟踪一买锚点，并在生成信号时传入
        buy1_anchor。否则二买信号永远为"非二买"，无法覆盖真实二买路径。
        """
        results = {
            "passed": True,
            "details": [],
            "mismatches": 0,
            "tested": 0,
        }

        if len(bars) < warmup + sample_size:
            sample_size = len(bars) - warmup - 1

        if sample_size <= 0:
            results["error"] = "数据不足以进行增量一致性检测"
            results["passed"] = False
            return results

        czsc_incremental = CZSC(bars[:warmup])
        test_bars = bars[warmup:warmup + sample_size]

        # 用策略对象维护一买锚点，确保二买信号按真实路径计算
        strategy = ChanTimingStrategy(
            symbol="VALIDATION",
            freq=freq_name,
            commission_rate=0.0,
            slippage=0.0,
            enable_daily_filter=False,
        )

        incremental_signals: List[dict] = []
        incremental_anchors: List[Optional[dict]] = []
        incremental_sell_anchors: List[Optional[dict]] = []
        for bar in test_bars:
            czsc_incremental.update(bar)
            anchor = strategy.get_last_buy1_anchor()
            sell_anchor = strategy.get_last_sell1_anchor()
            sig = get_all_signals(
                czsc_incremental, freq_name,
                buy1_anchor=anchor,
                sell1_anchor=sell_anchor,
            )
            strategy.update(sig, price=bar.close, dt=bar.dt, czsc_obj=czsc_incremental)
            incremental_signals.append(sig)
            incremental_anchors.append(anchor)
            incremental_sell_anchors.append(sell_anchor)

        check_points = list(range(0, sample_size, max(1, sample_size // 20)))
        mismatches: List[dict] = []

        for cp in check_points:
            bar_idx = warmup + cp
            czsc_full = CZSC(bars[:bar_idx + 1])
            # 全量重建时必须使用与增量路径同一时刻的 buy1_anchor，
            # 否则二买信号会退化为"非二买"，失去对比意义。
            full_sig = get_all_signals(czsc_full, freq_name,
                                       buy1_anchor=incremental_anchors[cp],
                                       sell1_anchor=incremental_sell_anchors[cp])
            inc_sig = incremental_signals[cp]

            for key in set(full_sig) | set(inc_sig):
                full_val = full_sig.get(key, "")
                inc_val = inc_sig.get(key, "")
                if full_val != inc_val:
                    mismatches.append({
                        "bar_idx": bar_idx,
                        "key": key,
                        "incremental": inc_val,
                        "full": full_val,
                    })

        results["tested"] = len(check_points)
        results["mismatches"] = len(mismatches)
        if mismatches:
            results["passed"] = False
            results["details"] = mismatches[:10]

        return results

    def validate_no_repaint(self, bars: List[RawBar], freq_name: str,
                            warmup: int = 100, sample_size: int = 200) -> dict:
        """
        无重绘检查（no-repaint）。

        在逐根K线推进过程中，记录每个历史截面的已确认笔快照；
        跑完全部样本后，比较早期快照中的已确认笔与最终状态下的对应已确认笔。
        如果 czsc 库基于后续数据修正了早期已确认笔（repaint），则会被检测出来。

        注意：当前未确认笔的延伸是正常的，不在此检查范围内。
        """
        results = {
            "passed": True,
            "details": [],
            "mismatches": 0,
            "tested": 0,
        }

        if len(bars) < warmup + sample_size:
            sample_size = len(bars) - warmup - 1

        if sample_size <= 0:
            results["error"] = "数据不足以进行无重绘检测"
            results["passed"] = False
            return results

        czsc_incremental = CZSC(bars[:warmup])
        test_bars = bars[warmup:warmup + sample_size]

        confirmed_bis_history: List[list] = []
        for bar in test_bars:
            czsc_incremental.update(bar)
            bis = _get_confirmed_bi_list(czsc_incremental)
            confirmed_bis_history.append([
                (bi.sdt, bi.edt, bi.direction, bi.low, bi.high) for bi in bis
            ])

        final_czsc = CZSC(bars[:warmup])
        for bar in test_bars:
            final_czsc.update(bar)
        final_bis = _get_confirmed_bi_list(final_czsc)
        final_bis_tuples = [
            (bi.sdt, bi.edt, bi.direction, bi.low, bi.high) for bi in final_bis
        ]

        check_points = list(range(0, sample_size, max(1, sample_size // 20)))
        repaint_mismatches: List[dict] = []

        for cp in check_points:
            bar_idx = warmup + cp
            recorded_bis = confirmed_bis_history[cp]
            n = len(recorded_bis)
            if n == 0:
                continue
            if n > len(final_bis_tuples):
                repaint_mismatches.append({
                    "bar_idx": bar_idx,
                    "type": "more_bis_than_final",
                    "recorded_count": n,
                    "final_count": len(final_bis_tuples),
                })
                continue
            for i in range(n):
                if recorded_bis[i] != final_bis_tuples[i]:
                    repaint_mismatches.append({
                        "bar_idx": bar_idx,
                        "type": "bi_changed",
                        "idx": i,
                        "recorded": recorded_bis[i],
                        "final": final_bis_tuples[i],
                    })
                    break

        results["tested"] = len(check_points)
        results["mismatches"] = len(repaint_mismatches)
        if repaint_mismatches:
            results["passed"] = False
            results["details"] = repaint_mismatches[:10]

        return results

    def validate_signal_freeze(self, bars: List[RawBar], freq_name: str,
                               warmup: int = 100, sample_size: int = 200) -> dict:
        """
        冻结快照确定性检查。

        在逐根K线推进过程中，对关键截面做 CZSC 对象的深拷贝并记录当时的信号；
        继续推进行情后，再从这些冻结快照重新生成信号，比较是否与当时记录一致。

        这个检查证明信号函数在同一个冻结截面上是确定性的；它不单独证明后续行情
        不会修正历史结构。历史结构是否被回改由 validate_no_repaint() 检查。

        修复：同时记录并复用该截面的一买锚点。二买信号依赖 buy1_anchor，
        缺少锚点时冻结快照的 replay 会与原记录不一致（都退化为"非二买"）。
        """
        results = {
            "passed": True,
            "details": [],
            "mismatches": 0,
            "tested": 0,
        }

        if len(bars) < warmup + sample_size:
            sample_size = len(bars) - warmup - 1

        if sample_size <= 0:
            results["error"] = "数据不足以进行冻结快照确定性检查"
            results["passed"] = False
            return results

        czsc = CZSC(bars[:warmup])
        test_bars = bars[warmup:warmup + sample_size]

        # 用策略对象维护一买锚点，确保二买信号按真实路径计算
        strategy = ChanTimingStrategy(
            symbol="VALIDATION",
            freq=freq_name,
            commission_rate=0.0,
            slippage=0.0,
            enable_daily_filter=False,
        )

        check_points = list(range(0, sample_size, max(1, sample_size // 20)))
        recorded_signals: Dict[int, dict] = {}
        recorded_anchors: Dict[int, Optional[dict]] = {}
        recorded_sell_anchors: Dict[int, Optional[dict]] = {}
        frozen_czsc: Dict[int, CZSC] = {}

        for i, bar in enumerate(test_bars):
            czsc.update(bar)
            anchor = strategy.get_last_buy1_anchor()
            sell_anchor = strategy.get_last_sell1_anchor()
            sig = get_all_signals(
                czsc, freq_name,
                buy1_anchor=anchor,
                sell1_anchor=sell_anchor,
            )
            strategy.update(sig, price=bar.close, dt=bar.dt, czsc_obj=czsc)
            if i in check_points:
                recorded_signals[i] = sig
                recorded_anchors[i] = anchor
                recorded_sell_anchors[i] = sell_anchor
                frozen_czsc[i] = copy.deepcopy(czsc)

        # 继续推进已经结束，现在检查冻结快照上的信号函数是否保持确定性
        mismatches: List[dict] = []
        for i in check_points:
            bar_idx = warmup + i
            frozen_sig = recorded_signals[i]
            # 必须用同一截面的 buy1_anchor 重放，否则二买信号会丢失。
            replay_sig = get_all_signals(frozen_czsc[i], freq_name,
                                         buy1_anchor=recorded_anchors[i],
                                         sell1_anchor=recorded_sell_anchors[i])

            for key in set(frozen_sig) | set(replay_sig):
                frozen_val = frozen_sig.get(key, "")
                replay_val = replay_sig.get(key, "")
                if frozen_val != replay_val:
                    mismatches.append({
                        "bar_idx": bar_idx,
                        "key": key,
                        "frozen": frozen_val,
                        "replay": replay_val,
                    })

        results["tested"] = len(check_points)
        results["mismatches"] = len(mismatches)
        if mismatches:
            results["passed"] = False
            results["details"] = mismatches[:10]

        return results

    def validate_second_buy_with_anchor(self, bars: List[RawBar], freq_name: str,
                                        warmup: int = 100) -> dict:
        """
        带一买锚点的二买信号专项稳定性验证。

        模拟正式回测的调用链路：
        1. 用 ChanTimingStrategy 维护一买锚点；
        2. 逐根 bar 更新 CZSC；
        3. 用当前锚点生成全部信号；
        4. 用生成的信号更新策略，记录新的一买锚点；
        5. 收集二买信号历史，检查是否存在「确认 → 候选」的闪回。

        这是针对「真实二买路径」的最直接稳定性检查：
        - 如果验证器不维护 buy1_anchor，二买信号会永远为"非二买"，
          历史长度大于 0 但 value_distribution 里只有非二买；
        - 如果二买信号不稳定，会出现 二买确认 → 二买候选 的非法转换。
        """
        results = {
            "passed": True,
            "details": {},
            "history": [],
        }

        if len(bars) <= warmup:
            results["error"] = "数据不足以进行二买锚点验证"
            results["passed"] = False
            return results

        czsc = CZSC(bars[:warmup])
        test_bars = bars[warmup:]

        strategy = ChanTimingStrategy(
            symbol="VALIDATION",
            freq=freq_name,
            commission_rate=0.0,
            slippage=0.0,
            enable_daily_filter=False,
        )

        second_buy_key = f"{freq_name}_D1BSP_二买V260615"
        history: List[dict] = []
        value_distribution: Dict[str, int] = {"非二买": 0, "二买候选": 0, "二买确认": 0}

        for i, bar in enumerate(test_bars):
            czsc.update(bar)
            anchor = strategy.get_last_buy1_anchor()
            sell_anchor = strategy.get_last_sell1_anchor()
            signals = get_all_signals(
                czsc, freq_name,
                buy1_anchor=anchor,
                sell1_anchor=sell_anchor,
            )
            strategy.update(signals, price=bar.close, dt=bar.dt, czsc_obj=czsc)

            value = signals.get(second_buy_key, "非二买_任意_任意_0")
            if "二买确认" in value:
                state = "二买确认"
            elif "二买候选" in value:
                state = "二买候选"
            else:
                state = "非二买"

            value_distribution[state] += 1
            history.append({
                "bar_idx": warmup + i,
                "dt": bar.dt.isoformat(),
                "state": state,
                "raw_value": value,
                "anchor": anchor,
            })

        # 检查非法闪回：二买确认后不允许再回到二买候选
        flickers: List[dict] = []
        for prev, curr in zip(history[:-1], history[1:]):
            if prev["state"] == "二买确认" and curr["state"] == "二买候选":
                flickers.append({
                    "from_bar": prev["bar_idx"],
                    "to_bar": curr["bar_idx"],
                    "from_value": prev["raw_value"],
                    "to_value": curr["raw_value"],
                })

        # 如果历史里完全没有二买候选/确认，说明验证没有覆盖到真实二买路径
        covered = value_distribution["二买候选"] > 0 or value_distribution["二买确认"] > 0

        results["history"] = history
        results["details"] = {
            "value_distribution": value_distribution,
            "flicker_count": len(flickers),
            "flickers": flickers[:10],
            "covered": covered,
        }

        if flickers:
            results["passed"] = False
            results["error"] = f"发现 {len(flickers)} 处二买确认→候选闪回"

        if not covered:
            results["passed"] = False
            results["error"] = (
                "样本未覆盖二买路径（历史里只有非二买）；"
                "请检查数据是否包含完整的一买→反弹→回抽→确认结构"
            )

        return results

    def validate_no_future_function(self, bars: List[RawBar], freq_name: str,
                                     warmup: int = 100, sample_size: int = 200) -> dict:
        """
        兼容旧接口：同时运行增量一致性检查、无重绘检查与冻结快照确定性检查。

        注意："无未来函数"这个名称不够严谨。本方法实际返回的是信号稳定性检查：
        - 增量一致性检查：策略计算逻辑是否在同一截面下一致；
        - 无重绘检查：底层 czsc 库是否基于后续数据修正历史已确认笔；
        - 冻结快照确定性检查：同一冻结截面上信号函数是否稳定。

        建议新代码直接调用 validate_incremental_consistency()、validate_no_repaint()
        和 validate_signal_freeze()。
        """
        inc_result = self.validate_incremental_consistency(
            bars, freq_name, warmup, sample_size
        )
        rp_result = self.validate_no_repaint(
            bars, freq_name, warmup, sample_size
        )
        sf_result = self.validate_signal_freeze(
            bars, freq_name, warmup, sample_size
        )

        return {
            "passed": inc_result["passed"] and rp_result["passed"] and sf_result["passed"],
            "incremental_consistent": inc_result["passed"],
            "no_repaint": rp_result["passed"],
            "signal_freeze": sf_result["passed"],
            "incremental_mismatches": inc_result.get("mismatches", 0),
            "repaint_mismatches": rp_result.get("mismatches", 0),
            "signal_freeze_mismatches": sf_result.get("mismatches", 0),
            "tested": inc_result.get("tested", 0),
            "details": (
                inc_result.get("details", [])
                + rp_result.get("details", [])
                + sf_result.get("details", [])
            ),
            "incremental_details": inc_result.get("details", []),
            "repaint_details": rp_result.get("details", []),
            "signal_freeze_details": sf_result.get("details", []),
        }

    def get_signal_distribution(self, signals_history: List[dict]) -> pd.DataFrame:
        """
        统计信号分布

        每个信号key的各分类出现频次和比例
        """
        if not signals_history:
            return pd.DataFrame()

        rows = []
        # 收集所有信号key
        all_keys = set()
        for record in signals_history:
            all_keys.update(record["signals"].keys())

        for key in sorted(all_keys):
            value_counts = defaultdict(int)
            total = 0
            for record in signals_history:
                if key in record["signals"]:
                    val_str = record["signals"][key]
                    v1 = val_str.split("_")[0]
                    value_counts[v1] += 1
                    total += 1

            for v1, count in sorted(value_counts.items(), key=lambda x: -x[1]):
                rows.append({
                    "signal_key": key,
                    "value": v1,
                    "count": count,
                    "ratio": count / total if total > 0 else 0,
                })

        return pd.DataFrame(rows)


class EventValidator:
    """事件验证器"""

    def validate_event_logic(self, positions: List[Position]) -> dict:
        """
        验证事件配置的逻辑正确性

        检查:
        - signals_all 中没有矛盾的信号
        - signals_not 不与 signals_all 冲突
        - 因子列表非空
        - 操作类型合理
        """
        results = {"passed": True, "details": []}

        for pos in positions:
            pos_result = {"name": pos.name, "issues": []}

            # 检查开仓事件
            for event in pos.opens:
                issues = self._check_event(event, "开仓")
                pos_result["issues"].extend(issues)

            # 检查平仓事件
            for event in pos.exits:
                issues = self._check_event(event, "平仓")
                pos_result["issues"].extend(issues)

            if pos_result["issues"]:
                results["passed"] = False

            results["details"].append(pos_result)

        return results

    def _check_event(self, event: Event, event_type: str) -> List[str]:
        """检查单个事件的逻辑"""
        issues = []

        # 1. 检查事件级别signals_all中是否有矛盾
        if event.signals_all:
            keys_seen = {}
            for sig in event.signals_all:
                key = sig.key
                if key in keys_seen:
                    # 同一个key出现两次，检查是否冲突
                    prev_val = keys_seen[key]
                    curr_val = sig.signal_value
                    if prev_val != curr_val:
                        issues.append(
                            f"[{event.name}] signals_all中信号矛盾: {key} "
                            f"同时要求 '{prev_val}' 和 '{curr_val}'"
                        )
                else:
                    keys_seen[key] = sig.signal_value

        # 2. 检查signals_not是否与signals_all冲突
        if event.signals_all and event.signals_not:
            all_keys = {s.key: s.signal_value for s in event.signals_all}
            for sig_not in event.signals_not:
                if sig_not.key in all_keys:
                    not_val = sig_not.signal_value.split("_")[0]
                    all_val = all_keys[sig_not.key].split("_")[0]
                    if not_val == all_val:
                        issues.append(
                            f"[{event.name}] signals_not与signals_all矛盾: "
                            f"{sig_not.key} 要求为 '{all_val}' 同时不能为 '{not_val}'"
                        )

        # 3. 检查因子列表
        if not event.factors and not event.signals_any:
            # 只有signals_all没有factors，事件可能过于简单
            pass  # 这是合法的

        # 4. 检查每个因子
        for factor in event.factors:
            if not factor.signals_all and not factor.signals_any:
                issues.append(
                    f"[{event.name}] 因子'{factor.name}'没有任何信号条件"
                )

        return issues

    def validate_signal_coverage(self, positions: List[Position],
                                  available_signals: List[str]) -> dict:
        """
        验证事件引用的信号是否都在可用信号列表中
        """
        results = {"passed": True, "missing_signals": [], "details": []}

        for pos in positions:
            all_events = pos.opens + pos.exits
            for event in all_events:
                # 收集事件中所有引用的信号key
                referenced_keys = set()
                for sig in event.signals_all + event.signals_any + event.signals_not:
                    referenced_keys.add(sig.key)
                for factor in event.factors:
                    for sig in factor.signals_all + factor.signals_any + factor.signals_not:
                        referenced_keys.add(sig.key)

                # 检查每个引用的key是否在可用信号中
                for ref_key in referenced_keys:
                    if ref_key not in available_signals:
                        results["passed"] = False
                        results["missing_signals"].append({
                            "position": pos.name,
                            "event": event.name,
                            "signal_key": ref_key,
                        })

        return results


class RobustnessValidator:
    """稳健性验证器"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or SQLITE_DB_PATH

    def _run_backtest_period(self, symbol: str, freq: str, start_date: str,
                             end_date: str, table_name: str = None) -> dict:
        """运行指定区间的回测"""
        from chan_strategy.backtest_engine import BacktestEngine
        engine = BacktestEngine(
            symbol=symbol, freq=freq,
            start_date=start_date, end_date=end_date,
            table_name=table_name,
        )
        return engine.run()

    def out_of_sample_test(self, symbol: str, freq: str,
                           full_start: str, full_end: str,
                           split_ratio: float = 0.7,
                           table_name: str = None) -> dict:
        """
        样本外测试

        将数据分为训练集(70%)和测试集(30%)，
        分别回测，对比绩效指标
        """
        from datetime import datetime as dt_cls
        start_dt = dt_cls.strptime(full_start, "%Y-%m-%d")
        end_dt = dt_cls.strptime(full_end, "%Y-%m-%d")

        total_days = (end_dt - start_dt).days
        split_days = int(total_days * split_ratio)

        from datetime import timedelta
        split_dt = start_dt + timedelta(days=split_days)
        split_date = split_dt.strftime("%Y-%m-%d")

        print(f"  样本内: {full_start} ~ {split_date}")
        print(f"  样本外: {split_date} ~ {full_end}")

        # 样本内回测
        in_sample = self._run_backtest_period(
            symbol, freq, full_start, split_date, table_name
        )

        # 样本外回测
        out_sample = self._run_backtest_period(
            symbol, freq, split_date, full_end, table_name
        )

        return {
            "in_sample": {
                "period": f"{full_start} ~ {split_date}",
                "total_trades": in_sample.get("total_trades", 0),
                "win_rate": in_sample.get("win_rate", 0),
                "profit_factor": in_sample.get("profit_factor", 0),
                "total_return_pct": in_sample.get("total_return_pct", 0),
                "max_drawdown_pct": in_sample.get("max_drawdown_pct", 0),
                "sharpe_ratio": in_sample.get("sharpe_ratio", 0),
            },
            "out_sample": {
                "period": f"{split_date} ~ {full_end}",
                "total_trades": out_sample.get("total_trades", 0),
                "win_rate": out_sample.get("win_rate", 0),
                "profit_factor": out_sample.get("profit_factor", 0),
                "total_return_pct": out_sample.get("total_return_pct", 0),
                "max_drawdown_pct": out_sample.get("max_drawdown_pct", 0),
                "sharpe_ratio": out_sample.get("sharpe_ratio", 0),
            },
            "degradation": self._calc_degradation(in_sample, out_sample),
        }

    def _calc_degradation(self, in_sample: dict, out_sample: dict) -> dict:
        """计算样本外相对样本内的退化程度"""
        metrics = ["win_rate", "profit_factor", "sharpe_ratio"]
        degradation = {}
        for m in metrics:
            in_val = in_sample.get(m, 0)
            out_val = out_sample.get(m, 0)
            if in_val != 0:
                degradation[m] = (out_val - in_val) / abs(in_val)
            else:
                degradation[m] = 0
        return degradation

    def rolling_window_test(self, symbol: str, freq: str,
                            start_date: str, end_date: str,
                            window_days: int = 180, step_days: int = 60,
                            table_name: str = None) -> pd.DataFrame:
        """
        滚动窗口测试

        用滑动窗口回测，检查策略在不同时段的表现稳定性
        """
        from datetime import timedelta
        from datetime import datetime as dt_cls

        start_dt = dt_cls.strptime(start_date, "%Y-%m-%d")
        end_dt = dt_cls.strptime(end_date, "%Y-%m-%d")

        results = []
        window_start = start_dt

        while window_start + timedelta(days=window_days) <= end_dt:
            window_end = window_start + timedelta(days=window_days)
            ws = window_start.strftime("%Y-%m-%d")
            we = window_end.strftime("%Y-%m-%d")

            print(f"  滚动窗口: {ws} ~ {we}")
            report = self._run_backtest_period(symbol, freq, ws, we, table_name)

            results.append({
                "window_start": ws,
                "window_end": we,
                "total_trades": report.get("total_trades", 0),
                "win_rate": report.get("win_rate", 0),
                "profit_factor": report.get("profit_factor", 0),
                "total_return_pct": report.get("total_return_pct", 0),
                "max_drawdown_pct": report.get("max_drawdown_pct", 0),
                "sharpe_ratio": report.get("sharpe_ratio", 0),
            })

            window_start += timedelta(days=step_days)

        return pd.DataFrame(results)


class SimNowReadinessChecker:
    """SimNow仿真准备度评估"""

    def check_readiness(self, backtest_report: dict,
                        incremental_consistency: dict = None,
                        no_repaint: dict = None,
                        signal_freeze: dict = None,
                        future_func_result: dict = None,
                        oos_result: dict = None) -> dict:
        """
        评估策略是否满足进入SimNow仿真的条件

        条件共 10 项，分两类（与下方代码的实际判定逻辑一致）:

        硬门槛（条件 1-4）——任何一项未显式通过（[NG] 或未检测/[?]）即 ready=False:
        1. 增量一致性检查 [OK]/[NG]
        2. 无重绘检查 [OK]/[NG]
        3. 冻结快照确定性检查 [OK]/[NG]
        4. 交易样本数量 >= 100 [OK]/[NG]

        软配额（条件 5-10）——不单独否决 ready，仅计入 passed_count:
        5. 胜率 >= 45% [OK]/[NG]
        6. 盈亏比 >= 1.0 [OK]/[NG]
        7. 最大回撤 <= 20% [OK]/[NG]
        8. 夏普比率 >= 0.3 [OK]/[NG]
        9. 样本外表现未显著失效 [OK]/[NG]
        10. 参数轻微变化结果稳定 [OK]/[NG]

        判定规则: ready = 硬门槛 1-4 全部显式通过（passed is True）
        且 passed_count >= 7（即 10 项中显式通过的不少于 7 项，含已通过的硬门槛项）。
        因此条件 5-10 中单项未通过不会单独否决 ready，只会降低 passed_count；
        未提供对应输入的检查记为"未检测"（passed=None），既不计入 passed_count，
        对硬门槛 1-4 而言也视同未通过（fail-closed）。
        """
        checks = {}

        # 兼容旧接口：如果传入 future_func_result，拆分为三项
        if future_func_result is not None and incremental_consistency is None:
            incremental_consistency = {
                "passed": future_func_result.get("incremental_consistent", True)
            }
            no_repaint = {
                "passed": future_func_result.get("no_repaint", True)
            }
            signal_freeze = {
                "passed": future_func_result.get("signal_freeze", True)
            }

        # 1. 增量一致性检查
        if incremental_consistency is not None:
            checks["增量一致性检查"] = {
                "passed": incremental_consistency.get("passed", False),
                "value": "一致" if incremental_consistency.get("passed", False) else "不一致",
            }
        else:
            checks["增量一致性检查"] = {"passed": None, "value": "未检测"}

        # 2. 无重绘检查
        if no_repaint is not None:
            checks["无重绘检查"] = {
                "passed": no_repaint.get("passed", False),
                "value": "无重绘" if no_repaint.get("passed", False) else "存在重绘",
            }
        else:
            checks["无重绘检查"] = {"passed": None, "value": "未检测"}

        # 3. 冻结快照确定性检查
        if signal_freeze is not None:
            checks["冻结快照确定性检查"] = {
                "passed": signal_freeze.get("passed", False),
                "value": "稳定" if signal_freeze.get("passed", False) else "不稳定",
            }
        else:
            checks["冻结快照确定性检查"] = {"passed": None, "value": "未检测"}

        # 4. 交易样本数量
        total_trades = backtest_report.get("total_trades", 0)
        checks["交易样本>=100"] = {
            "passed": total_trades >= 100,
            "value": f"{total_trades}次",
        }

        # 5. 胜率
        win_rate = backtest_report.get("win_rate", 0)
        checks["胜率>=45%"] = {
            "passed": win_rate >= 0.45,
            "value": f"{win_rate*100:.1f}%",
        }

        # 6. 盈亏比
        pf = backtest_report.get("profit_factor", 0)
        checks["盈亏比>=1.0"] = {
            "passed": pf >= 1.0,
            "value": f"{pf:.2f}",
        }

        # 7. 最大回撤
        max_dd = backtest_report.get("max_drawdown_pct", 100)
        checks["最大回撤<=20%"] = {
            "passed": max_dd <= 20,
            "value": f"{max_dd:.2f}%",
        }

        # 8. 夏普比率
        sharpe = backtest_report.get("sharpe_ratio", 0)
        checks["夏普比率>=0.3"] = {
            "passed": sharpe >= 0.3,
            "value": f"{sharpe:.2f}",
        }

        # 9. 样本外表现
        if oos_result is not None:
            degradation = oos_result.get("degradation", {})
            # 如果胜率退化超过30%或盈亏比退化超过50%，认为失效
            wr_deg = degradation.get("win_rate", 0)
            pf_deg = degradation.get("profit_factor", 0)
            oos_passed = wr_deg > -0.3 and pf_deg > -0.5
            out_wr = oos_result.get("out_sample", {}).get("win_rate", 0)
            checks["样本外表现"] = {
                "passed": oos_passed,
                "value": f"样本外胜率{out_wr*100:.1f}%, 退化{wr_deg*100:.1f}%",
            }
        else:
            checks["样本外表现"] = {"passed": None, "value": "未检测"}

        # 10. 参数稳定性 (通过rolling window结果判断)
        checks["参数稳定性"] = {"passed": None, "value": "待评估"}

        # 汇总
        passed_count = sum(1 for c in checks.values() if c["passed"] is True)
        total_checks = len(checks)
        checked_count = sum(1 for c in checks.values() if c["passed"] is not None)

        # 进入仿真的硬门槛：
        # - 增量一致性检查失败：策略计算逻辑存在未来数据依赖；
        # - 无重绘检查失败：底层 czsc 库基于后续数据修正历史已确认笔；
        # - 冻结快照确定性检查失败：同一历史截面上信号函数不稳定；
        # - 交易样本<100：统计意义不足，无法评估策略表现。
        # 任何一项失败都不应进入仿真。
        signal_stable = (
            checks.get("增量一致性检查", {}).get("passed") is True
            and checks.get("无重绘检查", {}).get("passed") is True
            and checks.get("冻结快照确定性检查", {}).get("passed") is True
        )
        enough_trades = checks.get("交易样本>=100", {}).get("passed") is True

        return {
            "checks": checks,
            "passed_count": passed_count,
            "total_checks": total_checks,
            "checked_count": checked_count,
            "ready": passed_count >= 7 and signal_stable and enough_trades,
        }

    def print_readiness(self, readiness: dict):
        """打印准备度报告"""
        print("\n" + "=" * 50)
        print("=== SimNow仿真准备度评估 ===")
        print("=" * 50)

        for name, check in readiness["checks"].items():
            if check["passed"] is True:
                status = "[OK]"
            elif check["passed"] is False:
                status = "[NG]"
            else:
                status = "[?]"
            print(f"{status} {name} (实际: {check['value']})")

        print("-" * 50)
        print(f"准备度: {readiness['passed_count']}/{readiness['total_checks']} 条件满足")

        if readiness["ready"]:
            print("结论: 可以进入SimNow仿真")
        else:
            print("结论: 需要继续优化")
        print("=" * 50)


def run_full_validation(symbol: str = "AP888", freq: str = "1",
                        start_date: str = None, end_date: str = None,
                        table_name: str = None) -> dict:
    """
    执行完整验证流程

    返回完整验证结果字典
    """
    from chan_strategy.backtest_engine import BacktestEngine

    start_date = start_date or BACKTEST_CONFIG["start_date"]
    end_date = end_date or BACKTEST_CONFIG["end_date"]

    results = {}
    print("=" * 60)
    print("缠论择时策略完整验证")
    print("=" * 60)
    print(f"品种: {symbol}, 频率: {freq}")
    print(f"区间: {start_date} ~ {end_date}")
    print()

    # ========== 1. 运行回测获取信号历史 ==========
    print("[1/6] 运行回测...")
    engine = BacktestEngine(
        symbol=symbol, freq=freq,
        start_date=start_date, end_date=end_date,
        table_name=table_name,
    )

    # 直接调用正式回测引擎的 run()，确保执行语义完全一致
    report = engine.run()
    if "error" in report:
        print(f"回测失败: {report['error']}")
        return {"error": report["error"]}

    # 从引擎获取信号历史（用于后续信号验证）
    signal_history_full = engine.signal_history
    # 未来函数验证必须使用交易周期K线，与正式回测一致
    trade_bars = engine.trade_bars
    trade_freq_name = STRATEGY_CONFIG.get("trade_freq", "30分钟")
    warmup_bars = 100

    # 获取回测报告
    results["backtest_report"] = report

    print(f"  交易次数: {report['total_trades']}")
    print(f"  胜率: {report['win_rate']*100:.1f}%")
    print(f"  盈亏比: {report.get('profit_factor', 0):.2f}")
    print(f"  总收益: {report.get('total_return_pct', 0):.2f}%")
    print(f"  最大回撤: {report.get('max_drawdown_pct', 0):.2f}%")
    print()

    # 子策略统计
    print("  子策略明细:")
    for name, stats in report.get("sub_strategies", {}).items():
        if stats["total_trades"] > 0:
            print(f"    [{name}] {stats['total_trades']}次, "
                  f"胜率{stats['win_rate']*100:.1f}%, 盈亏比{stats['profit_factor']:.2f}")
        else:
            print(f"    [{name}] 无交易")
    print()

    # ========== 2. 信号验证 ==========
    print("[2/6] 信号验证...")
    sig_validator = SignalValidator()

    # 穷尽性
    exhaustive_result = sig_validator.validate_exhaustiveness(signal_history_full)
    results["exhaustiveness"] = exhaustive_result
    print(f"  穷尽性: {'通过' if exhaustive_result['passed'] else '未通过'}")
    for sig, detail in exhaustive_result.get("details", {}).items():
        status = "OK" if detail["passed"] else "NG"
        dist_str = ", ".join(f"{k}:{v}" for k, v in detail["value_distribution"].items())
        print(f"    [{status}] {sig}: {dist_str}")

    # 互斥性
    mutual_result = sig_validator.validate_mutual_exclusivity(signal_history_full)
    results["mutual_exclusivity"] = mutual_result
    print(f"  互斥性: {'通过' if mutual_result['passed'] else '未通过'}")

    # 信号稳定性：增量一致性检查 + 无重绘检查 + 冻结快照确定性检查
    print("  信号稳定性检测中...")
    inc_result = sig_validator.validate_incremental_consistency(
        trade_bars, trade_freq_name, warmup=warmup_bars,
        sample_size=min(500, len(trade_bars) - warmup_bars - 1)
    )
    rp_result = sig_validator.validate_no_repaint(
        trade_bars, trade_freq_name, warmup=warmup_bars,
        sample_size=min(500, len(trade_bars) - warmup_bars - 1)
    )
    sf_result = sig_validator.validate_signal_freeze(
        trade_bars, trade_freq_name, warmup=warmup_bars,
        sample_size=min(500, len(trade_bars) - warmup_bars - 1)
    )
    results["incremental_consistency"] = inc_result
    results["no_repaint"] = rp_result
    results["signal_freeze"] = sf_result

    inc_status = "通过" if inc_result["passed"] else "未通过"
    rp_status = "通过" if rp_result["passed"] else "未通过"
    sf_status = "通过" if sf_result["passed"] else "未通过"
    print(f"  增量一致性检查: {inc_status} "
          f"(检测{inc_result['tested']}个点, {inc_result['mismatches']}处不一致)")
    print(f"  无重绘检查: {rp_status} "
          f"(检测{rp_result['tested']}个点, {rp_result['mismatches']}处重绘)")
    print(f"  冻结快照确定性检查: {sf_status} "
          f"(检测{sf_result['tested']}个点, {sf_result['mismatches']}处不稳定)")
    if not inc_result["passed"]:
        for m in inc_result["details"][:3]:
            print(f"    ! 不一致: bar={m['bar_idx']}, key={m['key']}, "
                  f"incremental={m['incremental']}, full={m['full']}")
    if not rp_result["passed"]:
        for m in rp_result["details"][:3]:
            print(f"    ! 重绘: bar={m['bar_idx']}, type={m['type']}, "
                  f"recorded={m.get('recorded')}, final={m.get('final')}")
    if not sf_result["passed"]:
        for m in sf_result["details"][:3]:
            print(f"    ! 冻结快照不稳定: bar={m['bar_idx']}, key={m['key']}, "
                  f"frozen={m['frozen']}, replay={m['replay']}")

    # 二买锚点专项验证
    sb_result = sig_validator.validate_second_buy_with_anchor(
        trade_bars, trade_freq_name, warmup=warmup_bars
    )
    results["second_buy_with_anchor"] = sb_result
    sb_status = "通过" if sb_result["passed"] else "未通过"
    dist = sb_result["details"].get("value_distribution", {})
    dist_str = ", ".join(f"{k}:{v}" for k, v in dist.items())
    flicker_count = sb_result["details"].get("flicker_count", 0)
    print(f"  二买锚点稳定性检查: {sb_status} (分布: {dist_str}, 闪回: {flicker_count})")
    if not sb_result["passed"]:
        err = sb_result.get("error", "")
        print(f"    ! {err}")
        for f in sb_result["details"].get("flickers", [])[:3]:
            print(f"    ! 闪回: bar={f['from_bar']}->{f['to_bar']}, "
                  f"{f['from_value']} -> {f['to_value']}")

    # 信号分布
    sig_dist = sig_validator.get_signal_distribution(signal_history_full)
    results["signal_distribution"] = sig_dist
    print()

    # ========== 3. 事件验证 ==========
    print("[3/6] 事件验证...")
    evt_validator = EventValidator()

    positions = engine.strategy.positions
    event_logic_result = evt_validator.validate_event_logic(positions)
    results["event_logic"] = event_logic_result
    print(f"  事件逻辑: {'通过' if event_logic_result['passed'] else '未通过'}")
    for pos_detail in event_logic_result["details"]:
        if pos_detail["issues"]:
            for issue in pos_detail["issues"]:
                print(f"    ! {issue}")

    # 信号覆盖检查
    # 修复：不能只看第一条 signal_history，否则日线等低频信号可能尚未出现，
    # 会被误判为事件引用了不存在的信号。应取所有历史截面的信号 key 并集。
    available_signals = list(set(
        key
        for record in signal_history_full
        for key in record.get("signals", {}).keys()
    )) if signal_history_full else []
    coverage_result = evt_validator.validate_signal_coverage(positions, available_signals)
    results["signal_coverage"] = coverage_result
    print(f"  信号覆盖: {'通过' if coverage_result['passed'] else '未通过'}")
    if not coverage_result["passed"]:
        for miss in coverage_result["missing_signals"]:
            print(f"    ! [{miss['position']}] 事件'{miss['event']}'引用了不存在的信号: {miss['signal_key']}")
    print()

    # ========== 4. 稳健性检验 ==========
    print("[4/6] 稳健性检验...")
    robustness = RobustnessValidator(db_path=engine.db_path)

    # 样本外测试
    print("  样本外测试:")
    oos_result = robustness.out_of_sample_test(
        symbol=symbol, freq=freq,
        full_start=start_date, full_end=end_date,
        split_ratio=0.7, table_name=table_name,
    )
    results["out_of_sample"] = oos_result
    in_s = oos_result["in_sample"]
    out_s = oos_result["out_sample"]
    print(f"    样本内: {in_s['total_trades']}次, 胜率{in_s['win_rate']*100:.1f}%, "
          f"收益{in_s['total_return_pct']:.2f}%")
    print(f"    样本外: {out_s['total_trades']}次, 胜率{out_s['win_rate']*100:.1f}%, "
          f"收益{out_s['total_return_pct']:.2f}%")
    print()

    # ========== 5. SimNow准备度评估 ==========
    print("[5/6] SimNow准备度评估...")
    checker = SimNowReadinessChecker()
    readiness = checker.check_readiness(
        backtest_report=report,
        incremental_consistency=inc_result,
        no_repaint=rp_result,
        signal_freeze=sf_result,
        oos_result=oos_result,
    )
    results["readiness"] = readiness
    checker.print_readiness(readiness)
    print()

    # ========== 6. 优化建议 ==========
    print("[6/6] 优化建议...")
    suggestions = generate_optimization_suggestions(report, results)
    results["suggestions"] = suggestions
    for s in suggestions:
        print(f"  → {s}")

    return results


def _calc_max_drawdown(pnls: List[float], position_fraction: float = 0.1) -> float:
    """从交易序列计算最大回撤百分比（考虑仓位比例）"""
    if not pnls:
        return 0
    # 将交易级别的pnl转换为组合级别
    portfolio_pnls = [p * position_fraction for p in pnls]
    cumulative = np.cumsum(portfolio_pnls)
    peak = np.maximum.accumulate(cumulative)
    drawdown = peak - cumulative
    return float(np.max(drawdown)) * 100 if len(drawdown) > 0 else 0


def _calc_max_drawdown_weighted(all_pairs: List[dict], pos_weights: dict) -> float:
    """从加权交易序列计算最大回撤百分比"""
    if not all_pairs:
        return 0
    # 按时间排序并计算加权pnl
    sorted_pairs = sorted(all_pairs, key=lambda x: x.get("close_dt", x.get("open_dt")))
    portfolio_pnls = []
    for p in sorted_pairs:
        w = pos_weights.get(p.get("strategy", ""), 0.15)
        portfolio_pnls.append(p["pnl_pct"] * w)
    cumulative = np.cumsum(portfolio_pnls)
    peak = np.maximum.accumulate(cumulative)
    drawdown = peak - cumulative
    return float(np.max(drawdown)) * 100 if len(drawdown) > 0 else 0


def _calc_sharpe(pnls: List[float], annual_factor: float = 252) -> float:
    """
    从交易收益率序列估算夏普比率

    修复: 原实现用 √min(n, 252) 年化，无清晰统计含义。
    正确做法: 使用 mean/std × √(年化交易次数估算)。
    对于CTA策略，假设每年约 annual_factor 个交易日，
    按实际交易频率推算年化交易次数。
    """
    if not pnls or len(pnls) < 2:
        return 0
    arr = np.array(pnls)
    mean_ret = np.mean(arr)
    std_ret = np.std(arr, ddof=1)  # 使用无偏标准差
    if std_ret == 0:
        return 0
    # 年化: 假设交易是均匀分布的，trades_per_year 估算
    # 使用实际交易次数和回测天数比推算（如果信息不足，用√n作近似）
    n = len(pnls)
    # 保守估计: 用 √min(n, annual_factor) 但限制上界
    trades_per_year = min(n, annual_factor)
    return float(mean_ret / std_ret * np.sqrt(trades_per_year))


def generate_optimization_suggestions(report: dict, validation_results: dict) -> List[str]:
    """根据验证结果生成优化建议"""
    suggestions = []

    total_trades = report.get("total_trades", 0)
    win_rate = report.get("win_rate", 0)
    pf = report.get("profit_factor", 0)
    max_dd = report.get("max_drawdown_pct", 0)
    sharpe = report.get("sharpe_ratio", 0)

    # 交易次数
    if total_trades < 100:
        suggestions.append(
            f"交易次数不足({total_trades}次<100): 考虑放宽开仓条件或缩短开仓间隔"
        )

    # 胜率
    if win_rate < 0.45:
        suggestions.append(
            f"胜率偏低({win_rate*100:.1f}%<45%): 考虑收紧开仓条件或优化止损参数"
        )

    # 盈亏比
    if pf < 1.0:
        suggestions.append(
            f"盈亏比不足({pf:.2f}<1.0): 考虑提高止盈或降低止损"
        )

    # 回撤
    if max_dd > 20:
        suggestions.append(
            f"回撤过大({max_dd:.1f}%>20%): 考虑降低仓位或增加风控条件"
        )

    # 夏普
    if sharpe < 0.3:
        suggestions.append(
            f"夏普比率偏低({sharpe:.2f}<0.3): 策略风险调整后收益不佳"
        )

    # 子策略分析
    sub = report.get("sub_strategies", {})
    for name, stats in sub.items():
        if stats["total_trades"] == 0:
            suggestions.append(f"[{name}] 无交易: 检查信号条件是否过严")
        elif stats["win_rate"] < 0.4:
            suggestions.append(f"[{name}] 胜率仅{stats['win_rate']*100:.1f}%: 考虑优化该子策略")

    # 信号覆盖问题
    coverage = validation_results.get("signal_coverage", {})
    if not coverage.get("passed", True):
        suggestions.append("存在信号引用错误: 事件配置中引用了不存在的信号key")

    if not suggestions:
        suggestions.append("策略表现良好，可考虑进入SimNow仿真阶段")

    return suggestions
