from __future__ import annotations

import json
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(r"D:\repo\vnpy\examples\czsc_strategy\skill_build")
SKILL = Path(r"C:\Users\Admin\.codex\skills\chan-pan-analysis")
EVAL_RECORDS = ROOT / "mapping" / "eval_records.jsonl"
DAILY = ROOT / "sh000001_daily.csv"
REPORT = ROOT / "reports" / "skill_comparison_10days.md"
NARRATIVE = SKILL / "references" / "signal_to_narrative.md"
FEWSHOT_MANIFEST = SKILL / "references" / "few_shot" / "manifest.json"
FEWSHOT_GAPS = SKILL / "references" / "few_shot" / "fewshot_gaps.json"
MAPPING_GAPS = SKILL / "references" / "mapping_gaps.json"
SEED = 20260616

UP_WORDS = ["向上", "上行", "上攻", "上涨", "多头", "反弹", "突破", "延续"]
DOWN_WORDS = ["向下", "下行", "调整", "回落", "破低", "弱", "跌破", "阴线"]
TERMS = [
    "一买", "二买", "三买", "一卖", "二卖", "三卖", "背驰", "中枢",
    "顶分型", "底分型", "盘整", "趋势", "线段", "缺口", "量能", "承接",
]


def run_analyzer(date: str) -> dict:
    cmd = [
        sys.executable,
        str(SKILL / "scripts" / "analyze_symbol.py"),
        "--symbol", "sh000001",
        "--csv", str(DAILY),
        "--asof", date,
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr or proc.stdout}
    return json.loads(proc.stdout)


def text_bias(text: str) -> str:
    up = sum(text.count(w) for w in UP_WORDS)
    down = sum(text.count(w) for w in DOWN_WORDS)
    if up > down * 1.25 and up >= 2:
        return "偏多/上行"
    if down > up * 1.25 and down >= 2:
        return "偏空/调整"
    if up or down:
        return "多空并陈/震荡"
    return "未明显表达"


def _bias_from_counts(up: int, down: int) -> str:
    if up > down * 1.25 and up >= 2:
        return "偏多/上行"
    if down > up * 1.25 and down >= 2:
        return "偏空/调整"
    if up or down:
        return "多空并陈/震荡"
    return "未明显表达"


def level_biases(text: str) -> dict[str, str]:
    """粗识别原文方向词主要落在哪个级别段落，减少日线 vs 分钟级错配误判。"""
    markers = [
        ("周线", ["上证周线走势结构", "周线走势结构", "周线"]),
        ("日线", ["上证日线走势结构", "日线走势结构", "日线"]),
        ("30分钟", ["上证30分钟走势结构", "30分钟走势结构", "30分钟", "30F"]),
        ("5分钟", ["上证5分钟走势结构", "5分钟走势结构", "5分钟", "5F"]),
        ("1分钟", ["上证1分钟走势结构", "1分钟走势结构", "1分钟", "1F"]),
    ]
    hits = []
    for level, pats in markers:
        positions = [text.find(p) for p in pats if text.find(p) >= 0]
        if positions:
            hits.append((min(positions), level))
    hits.sort()
    out = {}
    for idx, (pos, level) in enumerate(hits):
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(text)
        segment = text[pos:end]
        up = sum(segment.count(w) for w in UP_WORDS)
        down = sum(segment.count(w) for w in DOWN_WORDS)
        out[level] = _bias_from_counts(up, down)
    return out


def level_mismatch_note(bias: str, daily_direction: str, level_bias: dict[str, str]) -> str:
    daily_bias = level_bias.get("日线")
    intraday = {k: v for k, v in level_bias.items() if k in {"1分钟", "5分钟", "30分钟"}}
    if daily_bias and daily_bias != "未明显表达":
        return f"原文日线倾向={daily_bias}"
    if intraday:
        detail = "，".join(f"{k}={v}" for k, v in intraday.items())
        if bias in {"偏多/上行", "偏空/调整"}:
            return f"原文方向词主要可能来自次级别({detail})"
    return ""


def find_terms(text: str) -> list[str]:
    return [t for t in TERMS if t in text]


def load_narrative_terms() -> dict[str, list[str]]:
    """Read signal_to_narrative.md and index significant words by state value."""
    mapping: dict[str, list[str]] = {}
    if not NARRATIVE.exists():
        return mapping
    in_state_words = False
    for line in NARRATIVE.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped == "## 状态显著词":
            in_state_words = True
            continue
        if stripped.startswith("## ") and stripped != "## 状态显著词":
            in_state_words = False
        if not in_state_words:
            continue
        m = re.match(r"^-\s*(.+?)\s*[→:]\s*(.+)$", stripped)
        if not m:
            continue
        state = m.group(1).strip()
        words = [w.strip() for w in re.split(r"[、,，]", m.group(2)) if w.strip()]
        if words:
            mapping[state] = words
    return mapping


def load_term_phrases() -> dict[str, str]:
    phrases: dict[str, str] = {}
    if not NARRATIVE.exists():
        return phrases
    in_phrases = False
    for line in NARRATIVE.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped == "## 术语短句素材":
            in_phrases = True
            continue
        if stripped.startswith("## ") and stripped != "## 术语短句素材":
            in_phrases = False
        if not in_phrases:
            continue
        m = re.match(r"^-\s*(.+?)(?:\s*\[(.+?)\])?\s*→\s*(.+)$", stripped)
        if m:
            phrases[m.group(1).strip()] = {
                "role": (m.group(2) or "结构解释").strip(),
                "phrase": m.group(3).strip(),
            }
    return phrases


def load_narrative_templates() -> list[dict]:
    templates: list[dict] = []
    if not NARRATIVE.exists():
        return templates
    for line in NARRATIVE.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^-\s*条件:\s*(.+?)\s*→\s*(.+)$", line.strip())
        if not m:
            continue
        conditions = {}
        for part in m.group(1).split("&"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            conditions[key.strip()] = value.strip()
        if conditions:
            priority = 80
            if any(k.startswith("预期态") for k in conditions):
                priority = 100
            elif any(k in conditions for k in ["背驰", "三买", "三卖", "多头风控", "空头风控"]):
                priority = 60
            if len(conditions) == 1 and "中枢位置" in conditions:
                priority = 40
            templates.append({"conditions": conditions, "template": m.group(2).strip(), "priority": priority})
    return templates


def enrich_daily_state(daily: dict) -> dict:
    enriched = dict(daily)
    ctx = daily.get("provisional_context") or {}
    if ctx.get("available"):
        enriched["预期态"] = ctx.get("relative_position")
        enriched["预期态边界"] = ctx.get("nearest_boundary")
    return enriched


def load_fewshot_manifest() -> list[dict]:
    if not FEWSHOT_MANIFEST.exists():
        return []
    return json.loads(FEWSHOT_MANIFEST.read_text(encoding="utf-8", errors="replace"))


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def pick_narrative_templates(daily: dict, templates: list[dict]) -> list[str]:
    state = enrich_daily_state(daily)
    matched = []
    for item in templates:
        if all(str(state.get(k, "")) == str(v) for k, v in item.get("conditions", {}).items()):
            matched.append(item)
    matched.sort(key=lambda x: -x.get("priority", 0))
    main = [m for m in matched if m.get("priority", 0) >= 80][:2]
    risk = [m for m in matched if m.get("priority", 0) < 80][:1]
    return [m["template"] for m in main + risk]


def template_tension(daily: dict) -> str:
    direction = daily.get("方向")
    position = daily.get("中枢位置")
    ctx_pos = (daily.get("provisional_context") or {}).get("relative_position")
    if direction == "向下" and position == "中枢上方":
        return "确认笔方向转弱，但价格仍在中枢上方，属于方向与位置存在张力。"
    if direction == "向上" and position == "中枢下方":
        return "确认笔方向修复，但结构位置仍在中枢下方，属于弱修复张力。"
    if position == "中枢上方" and ctx_pos == "中枢下方":
        return "确认结构偏强，但最新价已跌到中枢下方，确认态与预期态冲突。"
    if position == "中枢下方" and ctx_pos == "中枢上方":
        return "确认结构偏弱，但最新价已站到中枢上方，确认态与预期态冲突。"
    return ""


def pick_narrative_words(daily: dict, narrative: dict[str, list[str]]) -> list[str]:
    words: list[str] = []
    for key in ["方向", "中枢位置", "背驰", "结构状态", "一买", "二买", "三买", "一卖", "二卖", "三卖"]:
        for word in narrative.get(str(daily.get(key, "")), []):
            if word not in words:
                words.append(word)
    return words[:8]


def words_to_phrases(words: list[str], term_phrases: dict[str, str]) -> list[str]:
    phrases = []
    used_roles = set()
    for word in words:
        meta = term_phrases.get(word)
        if not meta:
            continue
        if isinstance(meta, str):
            role, phrase = "结构解释", meta
        else:
            role, phrase = meta.get("role", "结构解释"), meta.get("phrase", "")
        if role in used_roles:
            continue
        if phrase and phrase not in phrases:
            phrases.append(phrase)
            used_roles.add(role)
    return phrases[:3]


def _active(value: str) -> bool:
    return bool(value) and not str(value).startswith("非") and value not in {"无", "不足", "未确认"}


def _fewshot_similarity(daily: dict, tags: dict) -> int:
    score = 0
    if daily.get("方向") == tags.get("方向"):
        score += 3
    if daily.get("中枢位置") == tags.get("中枢位置"):
        score += 3
    if daily.get("背驰") == tags.get("背驰"):
        score += 2
    for key in ["一买", "二买", "三买", "一卖", "二卖", "三卖"]:
        if _active(daily.get(key)) and daily.get(key) == tags.get(key):
            score += 3
        elif _active(daily.get(key)) and _active(tags.get(key)):
            score += 1
    for key in ["多头风控", "空头风控"]:
        if daily.get(key) == tags.get(key):
            score += 1
    return score


def pick_fewshot_refs(daily: dict, manifest: list[dict]) -> list[str]:
    active = []
    for key in ["一买", "二买", "三买", "一卖", "二卖", "三卖"]:
        value = daily.get(key)
        if _active(value):
            active.append(key)
    scored = []
    for item in manifest:
        sim = _fewshot_similarity(daily, item.get("state_tags", {}))
        terms = set(item.get("buy_sell_terms", []))
        if active and any(t in terms for t in active):
            sim += 2
        scored.append((sim, item))
    scored.sort(key=lambda x: (-x[0], -x[1].get("score", 0)))
    return [
        f"{item.get('date')}《{item.get('title', '')}》(sim={sim})"
        for sim, item in scored[:2]
    ]


def level_line(level: dict) -> str:
    zs = level.get("中枢") or {}
    zs_text = "无中枢" if not zs else f"中枢 ZG={zs.get('zg')} ZD={zs.get('zd')}（{zs.get('n_bis')}笔）"
    return (
        f"方向={level.get('方向', '-')}，位置={level.get('中枢位置', '-')}，"
        f"{zs_text}，背驰={level.get('背驰', '-')}，结构={level.get('结构状态', '-')}，"
        f"趋势={level.get('趋势方向', '-')}。"
    )


def make_skill_analysis(result: dict, narrative: dict[str, list[str]], templates: list[dict],
                        term_phrases: dict[str, str], fewshots: list[dict]) -> tuple[str, list[str], list[str], list[str], list[str]]:
    if "error" in result:
        return f"分析失败：{result['error']}", [], [], [], []

    daily = result.get("levels", {}).get("日线", {})
    zs = daily.get("中枢") or {}
    ctx = daily.get("provisional_context") or {}
    buy = f"一买={daily.get('一买', '-')}，二买={daily.get('二买', '-')}，三买={daily.get('三买', '-')}"
    sell = f"一卖={daily.get('一卖', '-')}，二卖={daily.get('二卖', '-')}，三卖={daily.get('三卖', '-')}"
    narrative_sentences = pick_narrative_templates(daily, templates)
    tension = template_tension(daily)
    narrative_words = pick_narrative_words(daily, narrative)
    narrative_phrases = words_to_phrases(narrative_words, term_phrases)
    fewshot_refs = pick_fewshot_refs(daily, fewshots)
    phrase = ""
    if narrative_sentences:
        phrase += " ".join(narrative_sentences)
    if narrative_phrases:
        phrase += " " + "。".join(narrative_phrases) + "。"
    elif narrative_words:
        phrase += f" 参考词：{'、'.join(narrative_words)}。"

    lines = [
        f"一、日线结构：{level_line(daily)}{phrase}",
        "二、次级别推演：指数 CSV 仅提供日线，本段降级；以下推演基于日线结构。",
        f"三、买卖点状态：多头 {buy}；空头 {sell}。",
        (
            f"四、强弱判断：背驰={daily.get('背驰', '-')}，"
            f"多头风控={daily.get('多头风控', '-')}，空头风控={daily.get('空头风控', '-')}；"
            "量能/板块需人工确认。"
        ),
    ]
    if ctx.get("available"):
        lines.append(
            f"预期态补充：最新收盘 {ctx.get('latest_close')} 位于{ctx.get('relative_position')}，"
            f"距离{ctx.get('nearest_boundary')}约 {ctx.get('distance_pct')}%；该字段不参与确认买卖点。"
        )
    if tension:
        lines.append(f"模板冲突提示：{tension}")
    watch_points = daily.get("watch_points") or {}
    watch_text = []
    for key in ["向上观察", "向下观察", "结构观察", "买卖点观察"]:
        values = watch_points.get(key) or []
        if values:
            watch_text.append(f"{key}：" + "；".join(values[:2]))
    if watch_text:
        lines.append("观察点：" + "；".join(watch_text) + "。")
    if zs:
        zg, zd = zs.get("zg"), zs.get("zd")
        lines.append(
            f"五、后续推演：第一种，站稳或重新突破 {zg}，结构转强并观察向上延续；"
            f"第二种，跌回或跌破 {zd}，中枢下沿失守，调整压力加大；"
            f"第三种，在 {zd}~{zg} 内反复，则按中枢震荡处理。"
        )
    else:
        key_prices = daily.get("关键价位") or []
        if key_prices:
            lines.append(
                f"五、后续推演：第一种，守住关键价位 {key_prices[0]} 后继续观察上行；"
                "第二种，跌破该价位则结构降级。"
            )
        else:
            lines.append("五、后续推演：关键价位不足，仅保留观察，不做强推演。")
    lines.append("免责声明：以上为缠论结构分析与推演，不构成投资建议。")
    return "\n".join(lines), narrative_words, narrative_phrases, narrative_sentences, fewshot_refs


def compare_record(record: dict, result: dict) -> tuple[list[str], str, str]:
    text = record["text"]
    terms = find_terms(text)
    bias = text_bias(text)
    daily = result.get("levels", {}).get("日线", {}) if "error" not in result else {}
    direction = daily.get("方向")
    position = daily.get("中枢位置")
    level_bias = level_biases(text)

    notes: list[str] = []
    if direction == "向上" and bias == "偏多/上行":
        notes.append("方向倾向一致")
    elif direction == "向下" and bias == "偏空/调整":
        notes.append("方向倾向一致")
    elif bias == "多空并陈/震荡":
        notes.append("原文多情景表达，skill 单点结构可作为客观锚")
    elif bias == "未明显表达":
        notes.append("原文方向词不明显，主要比较结构词")
    else:
        mismatch = level_mismatch_note(bias, direction, level_bias)
        if mismatch:
            notes.append(f"方向可能存在级别错配：原文={bias}，skill日线方向={direction}，{mismatch}")
        else:
            notes.append(f"方向可能有差异：原文={bias}，skill日线方向={direction}")

    if "中枢" in terms and position:
        notes.append(f"均涉及中枢/位置，skill={position}")
    if "背驰" in terms:
        notes.append(f"原文提背驰，skill背驰={daily.get('背驰')}")

    active_states = []
    for key in ["一买", "二买", "三买", "一卖", "二卖", "三卖", "背驰"]:
        value = daily.get(key)
        if value and not str(value).startswith("非") and value != "无":
            active_states.append(f"{key}:{value}")
    if active_states:
        notes.append("skill 买卖点/阶段态：" + "，".join(active_states))
    else:
        notes.append("skill 未给出确认买卖点，多为非确认或无背驰状态")

    return terms, bias, "；".join(notes)


def score_record(record: dict, result: dict, comparison: str, narrative_sentences: list[str]) -> dict:
    text = record.get("text", "")
    daily = result.get("levels", {}).get("日线", {}) if "error" not in result else {}
    terms = set(find_terms(text))
    score = {
        "direction_ok": "方向倾向一致" in comparison,
        "multi_scenario_ok": "多情景" in comparison,
        "direction_diff": "差异" in comparison,
        "level_mismatch": "级别错配" in comparison,
        "template_tension": bool(template_tension(daily)),
        "term_overlap": 0,
        "template_used": bool(narrative_sentences),
        "watch_points_used": any((daily.get("watch_points") or {}).values()),
        "bsp_watch_used": bool((daily.get("watch_points") or {}).get("买卖点观察")),
        "provisional_used": bool((daily.get("provisional_context") or {}).get("available")),
        "downgrade_ok": not result.get("minute_available", False),
    }
    for key in ["一买", "二买", "三买", "一卖", "二卖", "三卖", "背驰", "中枢"]:
        value = daily.get(key) if key != "中枢" else daily.get("中枢")
        if key in terms and value:
            score["term_overlap"] += 1
    return score


def main() -> None:
    records = [json.loads(line) for line in EVAL_RECORDS.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_date = {r["date"]: r for r in records}
    daily_dates = set(pd.to_datetime(pd.read_csv(DAILY)["datetime"]).dt.strftime("%Y-%m-%d"))
    narrative = load_narrative_terms()
    templates = load_narrative_templates()
    term_phrases = load_term_phrases()
    fewshots = load_fewshot_manifest()
    fewshot_gaps = load_json(FEWSHOT_GAPS, [])
    mapping_gaps = load_json(MAPPING_GAPS, [])

    eligible = sorted(
        d for d, r in by_date.items()
        if d in daily_dates and r.get("article_type") == "market_review"
    )
    sampled = sorted(random.Random(SEED).sample(eligible, 10))

    rows = []
    for date in sampled:
        record = by_date[date]
        result = run_analyzer(date)
        terms, bias, comparison = compare_record(record, result)
        analysis, narrative_words, narrative_phrases, narrative_sentences, fewshot_refs = make_skill_analysis(
            result, narrative, templates, term_phrases, fewshots)
        auto_score = score_record(record, result, comparison, narrative_sentences)
        rows.append((date, record, result, analysis, terms, bias, comparison,
                     narrative_words, narrative_phrases, narrative_sentences, fewshot_refs, auto_score))

    md: list[str] = [
        "# chan-pan-analysis 随机 10 天对比测试报告",
        "",
        "> 本报告是客观层连通性与模板生成检查；完整 LLM 叙事质量仍需在实际 Codex/Claude 调用中做人工留出评估。",
        "",
        f"- 随机种子: `{SEED}`",
        f"- 抽样范围: 留出集 eval_records ∩ 上证指数日线交易日 ∩ market_review，共 `{len(eligible)}` 天",
        f"- 样本日期: {', '.join(sampled)}",
        "- 数据源: `mapping/eval_records.jsonl` + `sh000001_daily.csv`",
        "- 调用方式: `C:\\Users\\Admin\\.codex\\skills\\chan-pan-analysis\\scripts\\analyze_symbol.py --symbol sh000001 --csv ... --asof <date>`",
        f"- 已读取 signal_to_narrative 状态数: `{len(narrative)}`；组合句式模板: `{len(templates)}`；术语短句: `{len(term_phrases)}`；few-shot manifest 条数: `{len(fewshots)}`",
        f"- few-shot 类别覆盖: `{dict(Counter(x.get('category') for x in fewshots)) if fewshots else {}}`",
        f"- few-shot 形态缺口: `{fewshot_gaps}`",
        f"- 话术映射缺口: `{[g.get('dimension') for g in mapping_gaps]}`",
        "",
        "## 自动评分",
        "",
        f"- 方向直接一致: `{sum(r[-1]['direction_ok'] for r in rows)}/{len(rows)}`",
        f"- 多情景可解释: `{sum(r[-1]['multi_scenario_ok'] for r in rows)}/{len(rows)}`",
        f"- 明显方向分歧: `{sum(r[-1]['direction_diff'] for r in rows)}/{len(rows)}`",
        f"- 级别错配提示: `{sum(r[-1]['level_mismatch'] for r in rows)}/{len(rows)}`",
        f"- 模板张力提示: `{sum(r[-1]['template_tension'] for r in rows)}/{len(rows)}`",
        f"- 使用组合句式: `{sum(r[-1]['template_used'] for r in rows)}/{len(rows)}`",
        f"- 输出预期态: `{sum(r[-1]['provisional_used'] for r in rows)}/{len(rows)}`",
        f"- 输出观察点: `{sum(r[-1]['watch_points_used'] for r in rows)}/{len(rows)}`",
        f"- 输出买卖点观察: `{sum(r[-1]['bsp_watch_used'] for r in rows)}/{len(rows)}`",
        f"- 原文关键词覆盖数: `{sum(r[-1]['term_overlap'] for r in rows)}`",
        "",
        "## 总览",
        "",
        "| 日期 | 原文标题 | 原文倾向 | skill日线方向 | skill中枢位置 | skill背驰 | 对比结论 |",
        "|---|---|---|---|---|---|---|",
    ]

    for date, record, result, _, _, bias, comparison, _, _, _, _, _ in rows:
        daily = result.get("levels", {}).get("日线", {}) if "error" not in result else {}
        title = (record.get("article_title") or record.get("doc_title") or "").replace("|", "/")
        md.append(
            f"| {date} | {title} | {bias} | {daily.get('方向', 'ERR')} | "
        f"{daily.get('中枢位置', 'ERR')} | {daily.get('背驰', 'ERR')} | {comparison.split('；')[0]} |"
        )

    md.extend(["", "## 逐日详情"])
    for idx, (date, record, result, analysis, terms, bias, comparison,
              narrative_words, narrative_phrases, narrative_sentences, fewshot_refs, auto_score) in enumerate(rows, 1):
        title = record.get("article_title") or record.get("doc_title") or ""
        text = record["text"]
        excerpt = re.sub(r"\s+", " ", text[:260]).strip()
        daily = result.get("levels", {}).get("日线", {}) if "error" not in result else {}
        zs = daily.get("中枢") or {}

        md.extend([
            "",
            f"### {idx}. {date}《{title}》",
            "",
            f"- 原文关键词: {', '.join(terms) if terms else '无明显关键词'}",
            f"- 原文倾向粗判: {bias}",
            f"- 原文级别倾向: {level_biases(text) or '未识别'}",
            f"- 语料类型: {record.get('article_type')}",
            f"- 使用组合句式: {' / '.join(narrative_sentences) if narrative_sentences else '无'}",
            f"- 使用短句素材: {' / '.join(narrative_phrases) if narrative_phrases else '无'}",
            f"- 使用映射词: {', '.join(narrative_words) if narrative_words else '无'}",
            f"- few-shot参考: {', '.join(fewshot_refs) if fewshot_refs else '无'}",
            f"- 自动评分: {auto_score}",
            f"- 原文摘录: {excerpt}...",
            "",
            "**skill 客观结构摘要**",
        ])
        if "error" in result:
            md.append(f"- ERROR: {result['error']}")
        else:
            ctx = daily.get("provisional_context") or {}
            watch_points = daily.get("watch_points") or {}
            md.extend([
                f"- asof: {result.get('asof')}; 日线方向={daily.get('方向')}; 中枢位置={daily.get('中枢位置')}; 背驰={daily.get('背驰')}; 结构={daily.get('结构状态')}",
                f"- 趋势方向: {daily.get('趋势方向')}; 模板张力={template_tension(daily) or '无'}",
                f"- 中枢: ZG={zs.get('zg')} ZD={zs.get('zd')} n_bis={zs.get('n_bis')}; 关键价位={daily.get('关键价位')}",
                f"- 预期态: available={ctx.get('available')} latest_close={ctx.get('latest_close')} relative={ctx.get('relative_position')} distance_pct={ctx.get('distance_pct')} note={ctx.get('note')}",
                f"- 观察点: {watch_points}",
                f"- 买点: 一买={daily.get('一买')} 二买={daily.get('二买')} 三买={daily.get('三买')}; 卖点: 一卖={daily.get('一卖')} 二卖={daily.get('二卖')} 三卖={daily.get('三卖')}",
            ])

        md.extend([
            "",
            "**按 skill 模板生成的分析**",
            "",
            analysis,
            "",
            "**对比点评**",
            "",
            f"- {comparison}",
        ])

    md.extend([
        "",
        "## 结论",
        "",
        "- skill 能稳定给出截至抽样日的日线客观结构、关键价位、买卖点状态和情景推演。",
        "- 与原文相比，skill 的优势是结构口径固定、不会编造分钟级；局限是当前指数 CSV 只有日线，原文中大量 1F/5F 推演、量能、板块轮动只能降级或标注需人工确认。",
        "- 本轮样本中若原文是多情景推演，skill 的单点日线状态更适合作为“结构锚”，不宜要求逐句复刻原文判断。",
    ])

    REPORT.write_text("\n".join(md), encoding="utf-8")
    print(REPORT)
    print(",".join(sampled))


if __name__ == "__main__":
    main()
