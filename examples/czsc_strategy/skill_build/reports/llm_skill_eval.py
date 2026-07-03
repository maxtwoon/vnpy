from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SKILL = Path(r"C:\Users\Admin\.codex\skills\chan-pan-analysis")
EVAL_RECORDS = ROOT / "mapping" / "eval_records.jsonl"
DAILY = ROOT / "sh000001_daily.csv"
DEFAULT_JSONL = ROOT / "reports" / "llm_skill_eval_results.jsonl"
DEFAULT_REPORT = ROOT / "reports" / "llm_skill_eval_report.md"
DEFAULT_TASKS = ROOT / "reports" / "llm_skill_eval_tasks.jsonl"
CONFIG_FILE = ROOT / "llm_eval_config.json"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
ALLOWED_DEEPSEEK_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}

UP_WORDS = ["向上", "上行", "上攻", "上涨", "多头", "反弹", "突破", "延续", "走强", "修复"]
DOWN_WORDS = ["向下", "下行", "调整", "回落", "破低", "弱", "跌破", "下跌", "走弱", "压力"]
STRUCTURE_TERMS = [
    "一买", "二买", "三买", "一卖", "二卖", "三卖", "背驰", "中枢",
    "顶分型", "底分型", "盘整", "趋势", "线段", "缺口", "量能", "承接",
    "离开段", "进入段", "震荡", "反抽", "回踩",
]
BUY_SELL_TERMS = ["一买", "二买", "三买", "一卖", "二卖", "三卖"]
LEVEL_MARKERS = [
    ("日线", ["上证日线走势结构", "日线走势结构", "日线"]),
    ("30分钟", ["上证30分钟走势结构", "30分钟走势结构", "30分钟", "30F"]),
    ("5分钟", ["上证5分钟走势结构", "5分钟走势结构", "5分钟", "5F"]),
    ("1分钟", ["上证1分钟走势结构", "1分钟走势结构", "1分钟", "1F"]),
]


def read_text(path: Path, limit: int | None = None) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if limit is not None and len(text) > limit:
        return text[:limit] + "\n...[truncated]"
    return text


def load_llm_config() -> dict[str, Any]:
    config = {
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "model": os.environ.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
        "base_url": DEFAULT_DEEPSEEK_BASE_URL,
    }
    if CONFIG_FILE.exists():
        file_config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        for key in ["api_key", "model"]:
            value = file_config.get(key)
            if value:
                config[key] = value
        configured_url = str(file_config.get("base_url") or "").strip().rstrip("/")
        if configured_url and configured_url != DEFAULT_DEEPSEEK_BASE_URL:
            raise ValueError(
                f"DeepSeek base_url is deprecated; use {DEFAULT_DEEPSEEK_BASE_URL} in {CONFIG_FILE}"
            )
    if config["model"] not in ALLOWED_DEEPSEEK_MODELS:
        raise ValueError(
            f"Unsupported DeepSeek model {config['model']!r}; "
            f"use one of {sorted(ALLOWED_DEEPSEEK_MODELS)}"
        )
    return config


def normalize_chat_completions_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if url != DEFAULT_DEEPSEEK_BASE_URL:
        raise ValueError(f"DeepSeek base_url is deprecated; use {DEFAULT_DEEPSEEK_BASE_URL}")
    return f"{url}/chat/completions"


def load_eval_records(start_date: str) -> list[dict[str, Any]]:
    records = []
    for line in EVAL_RECORDS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("date", "") >= start_date and record.get("article_type") == "market_review":
            records.append(record)
    return records


def load_daily_dates() -> set[str]:
    with DAILY.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        dates = set()
        for row in reader:
            dt = row.get("datetime") or row.get("dt") or row.get("date")
            if dt:
                dates.add(str(dt)[:10])
        return dates


def run_analyzer(date: str) -> dict[str, Any]:
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
        timeout=90,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or proc.stdout.strip()}
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


def find_terms(text: str) -> set[str]:
    return {term for term in STRUCTURE_TERMS if term in text}


def find_buy_sell_terms(text: str) -> set[str]:
    return {term for term in BUY_SELL_TERMS if term in text}


def _has_near_keyword(text: str, start: int, keywords: list[str], window: int = 8) -> bool:
    left = max(0, start - window)
    right = min(len(text), start + window)
    segment = text[left:right]
    return any(word in segment for word in keywords)


def classify_buy_sell_mentions(text: str) -> dict[str, list[str]]:
    """Classify buy/sell wording without treating negative states as claims.

    Examples:
    - "一买=非一买" -> no confirmed claim
    - "当前无确认买卖点" -> no confirmed claim
    - "三买确认" / "一卖成立" -> confirmed claim
    - "观察类二买" / "潜在三卖" -> candidate mention
    """
    confirmed: set[str] = set()
    candidates: set[str] = set()
    neg_words = ["非", "无", "未", "不是", "不构成", "没有", "暂无", "暂不", "不成立", "缺乏", "缺少", "不列为"]
    candidate_words = ["候选", "观察", "潜在", "类", "疑似", "可能", "进入观察", "等待", "如果", "若", "才", "则"]

    for term in BUY_SELL_TERMS:
        for match in re.finditer(re.escape(term), text):
            start = match.start()
            local = text[max(0, start - 18): min(len(text), start + len(term) + 18)]
            is_negative = any(word in local for word in neg_words)
            is_conditional = any(word in local for word in candidate_words)
            direct_confirm = bool(
                re.search(rf"{re.escape(term)}\s*(确认|成立)", local)
                or re.search(rf"(确认|有效|标准)\s*(的)?\s*{re.escape(term)}", local)
            )
            if is_negative:
                continue
            if direct_confirm and not is_conditional:
                confirmed.add(term)
            elif is_conditional:
                candidates.add(term)
    return {
        "confirmed": sorted(confirmed),
        "candidate": sorted(candidates - confirmed),
        "all": sorted(confirmed | candidates | find_buy_sell_terms(text)),
    }


def direction_match(generated: str, human: str) -> str:
    gen_bias = text_bias(generated)
    human_bias = text_bias(human)
    if gen_bias == human_bias and gen_bias != "未明显表达":
        return "direct"
    if "多空并陈" in {gen_bias, human_bias}:
        return "scenario"
    if gen_bias == "未明显表达" or human_bias == "未明显表达":
        return "unclear"
    return "diff"


def level_biases(text: str) -> dict[str, str]:
    hits = []
    for level, markers in LEVEL_MARKERS:
        positions = [text.find(marker) for marker in markers if text.find(marker) >= 0]
        if positions:
            hits.append((min(positions), level))
    hits.sort()
    out: dict[str, str] = {}
    for idx, (pos, level) in enumerate(hits):
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(text)
        out[level] = text_bias(text[pos:end])
    return out


def direction_attribution(generated: str, human: str, result: dict[str, Any]) -> str:
    gen_bias = text_bias(generated)
    human_bias = text_bias(human)
    human_levels = level_biases(human)
    daily_human = human_levels.get("日线")
    intraday_biases = [v for k, v in human_levels.items() if k in {"1分钟", "5分钟", "30分钟"}]

    if daily_human and daily_human != "未明显表达":
        if daily_human == gen_bias or gen_bias == "多空并陈/震荡":
            return "daily_match"
        return "true_conflict"
    if intraday_biases and any(v != "未明显表达" for v in intraday_biases):
        if human_bias != gen_bias:
            return "intraday_mismatch"
        return "scenario_match"
    match = direction_match(generated, human)
    if match == "direct":
        return "daily_match"
    if match == "scenario":
        return "scenario_match"
    if match == "unclear":
        return "unclear"
    return "true_conflict"


def collect_objective_states(result: dict[str, Any]) -> dict[str, str]:
    daily = (result.get("levels") or {}).get("日线") or {}
    return {k: str(daily.get(k, "")) for k in BUY_SELL_TERMS}


def active_buy_sell_terms(result: dict[str, Any]) -> set[str]:
    states = collect_objective_states(result)
    active = set()
    for key, value in states.items():
        if value and not value.startswith("非") and value not in {"无", "不足", "未确认", "None"}:
            active.add(key)
    return active


def extract_numbers(text: str) -> list[float]:
    numbers = []
    for match in re.finditer(r"(?<![\w.])[-+]?\d{2,5}(?:\.\d+)?(?![\w.])", text):
        try:
            numbers.append(float(match.group(0)))
        except ValueError:
            pass
    return numbers


def objective_numbers(value: Any) -> list[float]:
    out: list[float] = []
    if isinstance(value, dict):
        for child in value.values():
            out.extend(objective_numbers(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(objective_numbers(child))
    elif isinstance(value, (int, float)):
        if abs(float(value)) >= 10:
            out.append(float(value))
    elif isinstance(value, str):
        out.extend(extract_numbers(value))
    return out


def unsourced_prices(generated: str, result: dict[str, Any], tolerance: float = 0.15) -> list[float]:
    allowed = objective_numbers(result)
    bad = []
    for num in extract_numbers(generated):
        if not any(abs(num - src) <= tolerance for src in allowed):
            bad.append(num)
    return sorted(set(bad))


def scenario_count(text: str) -> int:
    patterns = ["第一种", "第二种", "第三种", "如果", "若", "则", "情景", "推演"]
    return sum(text.count(p) for p in patterns)


def score_generated(generated: str, human: str, result: dict[str, Any]) -> dict[str, Any]:
    human_terms = find_terms(human)
    gen_terms = find_terms(generated)
    objective_active = active_buy_sell_terms(result)
    gen_bsp = classify_buy_sell_mentions(generated)
    human_bsp = classify_buy_sell_mentions(human)
    gen_confirmed = set(gen_bsp["confirmed"])
    human_confirmed = set(human_bsp["confirmed"])
    invented_confirmed = sorted(t for t in gen_confirmed if t not in objective_active and t not in human_confirmed)
    return {
        "direction": direction_match(generated, human),
        "direction_attribution": direction_attribution(generated, human, result),
        "generated_bias": text_bias(generated),
        "human_bias": text_bias(human),
        "term_overlap": len(gen_terms & human_terms),
        "generated_terms": sorted(gen_terms),
        "human_terms": sorted(human_terms),
        "buy_sell_overlap": len(gen_confirmed & human_confirmed),
        "objective_active_buy_sell": sorted(objective_active),
        "confirmed_bsp_claims": sorted(gen_confirmed),
        "candidate_bsp_mentions": gen_bsp["candidate"],
        "human_confirmed_bsp": sorted(human_confirmed),
        "invented_confirmed_bsp": invented_confirmed,
        "invented_buy_sell_terms": invented_confirmed,
        "scenario_count": scenario_count(generated),
        "unsourced_prices": unsourced_prices(generated, result),
    }


def render_template_baseline(result: dict[str, Any]) -> str:
    if "error" in result:
        return f"分析失败：{result['error']}"
    daily = (result.get("levels") or {}).get("日线") or {}
    zs = daily.get("中枢") or {}
    ctx = daily.get("provisional_context") or {}
    watch = daily.get("watch_points") or {}
    zline = "暂无有效中枢"
    if zs:
        zline = f"中枢 ZG={zs.get('zg')}，ZD={zs.get('zd')}，n_bis={zs.get('n_bis')}，位置={daily.get('中枢位置')}"
    lines = [
        f"一、日线结构：确认笔方向={daily.get('方向')}，趋势方向={daily.get('趋势方向')}，{zline}，背驰={daily.get('背驰')}，结构={daily.get('结构状态')}。",
        "二、次级别推演：指数历史分钟数据未作为本轮输入，本段降级为日线结构推演。",
        (
            f"三、买卖点状态：一买={daily.get('一买')}，二买={daily.get('二买')}，三买={daily.get('三买')}；"
            f"一卖={daily.get('一卖')}，二卖={daily.get('二卖')}，三卖={daily.get('三卖')}。"
        ),
        f"四、强弱判断：多头风控={daily.get('多头风控')}，空头风控={daily.get('空头风控')}；量能与板块轮动需人工确认。",
    ]
    if ctx.get("available"):
        lines.append(
            f"预期态补充：最新收盘 {ctx.get('latest_close')} 位于{ctx.get('relative_position')}，"
            f"距离{ctx.get('nearest_boundary')}约 {ctx.get('distance_pct')}%。"
        )
    if watch:
        watch_text = []
        for key, values in watch.items():
            if values:
                watch_text.append(f"{key}：" + "；".join(map(str, values[:2])))
        if watch_text:
            lines.append("观察点：" + "；".join(watch_text) + "。")
    if zs:
        lines.append(
            f"五、后续推演：第一种，重新站稳或突破 {zs.get('zg')}，结构转强；"
            f"第二种，跌破或不能收回 {zs.get('zd')}，调整压力加大；"
            f"第三种，在 {zs.get('zd')}~{zs.get('zg')} 内震荡，按中枢震荡处理。"
        )
    else:
        lines.append("五、后续推演：关键结构不足，保留观察，不强行给出买卖点结论。")
    lines.append("以上为缠论结构分析与推演，不构成投资建议。")
    return "\n".join(lines)


def load_fewshot_examples(limit: int = 8, chars_per_file: int = 1100) -> str:
    manifest_path = SKILL / "references" / "few_shot" / "manifest.json"
    if not manifest_path.exists():
        return ""
    items = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = items[:limit]
    parts = []
    for item in selected:
        file_name = item.get("file")
        path = SKILL / "references" / "few_shot" / str(file_name)
        if not path.exists():
            continue
        body = read_text(path, chars_per_file)
        parts.append(
            f"### {item.get('category')} | {item.get('date')} | {file_name}\n"
            f"state_tags={json.dumps(item.get('state_tags', {}), ensure_ascii=False)}\n{body}"
        )
    return "\n\n".join(parts)


def build_prompt(record: dict[str, Any], result: dict[str, Any]) -> str:
    skill_md = read_text(SKILL / "SKILL.md", 7000)
    signal_map = read_text(SKILL / "references" / "signal_to_narrative.md", 9000)
    template = read_text(SKILL / "references" / "解盘模板.md", 4000)
    terms = read_text(SKILL / "references" / "缠论术语表.md", 5000)
    fewshots = load_fewshot_examples()
    objective_json = json.dumps(result, ensure_ascii=False, indent=2)
    human_excerpt = re.sub(r"\s+", " ", record.get("text", "")[:900]).strip()
    return f"""你是 chan-pan-analysis skill 的执行者。请真实遵守下面的 SKILL.md、映射表、模板和 few-shot，
基于客观 JSON 给出 {record.get('date')} 上证指数日线解盘。不要引用或复述真人原文，真人原文只在评估阶段使用。

硬约束：
1. 所有方向、中枢、背驰、买卖点、关键价位必须来自客观 JSON。
2. 不允许编造 JSON 之外的价格、分钟级结构、量能和板块轮动。
3. 如果 minute_available=false，次级别必须降级。
4. 日线级二买/二卖缺少有效确认样本，除非 JSON 明确给出，否则只作为观察条件，不写成确认买卖点。
5. 不得输出任何 JSON 中不存在的整数心理关口、整数目标位或概略价位；如果要描述这类位置，只能写“上方整数关口需人工确认”，不能给出具体数值。
6. 不得把 JSON 中的价位四舍五入、取整或改写成“4000附近/整数关口/约某点”；必须使用 JSON 原值，或只写“中枢下沿附近”这类无数字表达。
7. 真人正文摘要里的数字也不能作为价位来源；只有同时出现在客观 JSON 的数字价位才允许写入解盘正文。
8. 背驰必须显式表述；即使客观 JSON 中 背驰=无，也要写“当前未见明显背驰”或同义表述。
9. 买卖点必须逐字遵守客观 JSON：JSON 写“非一买/非二买/非三买/非一卖/非二卖/非三卖”时，只能写“非…”或“当前无确认…”，不得改写成“候选、确认过程、观察状态、潜在结构、可形成某买卖点”。
10. 只有 JSON 的买卖点字段本身包含“候选、确认、离开中枢、回抽不入中枢”等非“非…”状态时，才允许使用对应候选/观察话术。
11. 不得用“方向向下 + 中枢下方”“离开段延续”“反抽未回中枢”等位置/方向信息自行推导一卖、二卖、三卖；买卖点只认客观 JSON 的对应买卖点字段。
12. 优先使用语料中的缠论术语和句式，例如“离开段 / 进入段 / 回抽不入中枢 / 中枢震荡 / 背驰 / 底分型 / 顶分型 / 强整理 / 温和调整”，避免泛化成普通金融话术。
13. 输出五段式，最后必须带“不构成投资建议”。

--- SKILL.md ---
{skill_md}

--- signal_to_narrative.md ---
{signal_map}

--- 解盘模板.md ---
{template}

--- 缠论术语表.md ---
{terms}

--- few-shot examples ---
{fewshots}

--- 客观 JSON ---
{objective_json}

--- 评估留存信息，不得复述 ---
日期：{record.get('date')}
真人标题：{record.get('article_title') or record.get('doc_title')}
真人正文摘要（仅用于理解语料风格，不得照抄）：{human_excerpt}
"""


def call_deepseek(prompt: str, api_key: str, base_url: str, model: str, max_tokens: int, temperature: float) -> str:
    if not api_key:
        raise RuntimeError(f"DeepSeek API key is not set; fill {CONFIG_FILE} or set DEEPSEEK_API_KEY")
    body = {
        "model": model,
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": "你是严格遵守客观 JSON 的缠论解盘评估生成器。"},
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        normalize_chat_completions_url(base_url),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"DeepSeek response has no choices: {payload}")
    message = choices[0].get("message") or {}
    return str(message.get("content", "")).strip()


def write_markdown_report(rows: list[dict[str, Any]], report_path: Path, dry_run: bool) -> None:
    evaluated = [r for r in rows if r.get("llm_text")]
    direction_counts = {}
    attribution_counts = {}
    for row in evaluated:
        key = row["llm_score"]["direction"]
        direction_counts[key] = direction_counts.get(key, 0) + 1
        attr = row["llm_score"].get("direction_attribution", "unknown")
        attribution_counts[attr] = attribution_counts.get(attr, 0) + 1

    def avg(name: str, rows_: list[dict[str, Any]], score_key: str) -> float:
        values = [r[score_key][name] for r in rows_ if isinstance(r.get(score_key), dict)]
        return float(sum(values) / len(values)) if values else 0.0

    md = [
        "# chan-pan-analysis LLM 真评估报告",
        "",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 模式: {'dry-run / 未调用 DeepSeek' if dry_run else 'DeepSeek 实际生成'}",
        f"- 样本数: `{len(rows)}`；LLM 已评估: `{len(evaluated)}`",
        f"- 数据源: `{EVAL_RECORDS}` + `{DAILY}`",
        f"- 输出 JSONL: `{DEFAULT_JSONL}`",
        "",
        "## 汇总",
        "",
        f"- LLM 方向分布: `{direction_counts}`",
        f"- LLM 方向归因: `{attribution_counts}`",
        f"- LLM 结构术语平均重合数: `{avg('term_overlap', evaluated, 'llm_score'):.2f}`",
        f"- LLM 买卖点平均重合数: `{avg('buy_sell_overlap', evaluated, 'llm_score'):.2f}`",
        f"- LLM 平均情景覆盖计数: `{avg('scenario_count', evaluated, 'llm_score'):.2f}`",
        f"- LLM 编造确认买卖点总数: `{sum(len(r['llm_score'].get('invented_confirmed_bsp', [])) for r in evaluated)}`",
        f"- 模板基线结构术语平均重合数: `{avg('term_overlap', rows, 'baseline_score'):.2f}`",
        f"- 模板基线买卖点平均重合数: `{avg('buy_sell_overlap', rows, 'baseline_score'):.2f}`",
        f"- 模板基线平均情景覆盖计数: `{avg('scenario_count', rows, 'baseline_score'):.2f}`",
        "",
        "## 逐日对比",
        "",
        "| 日期 | 标题 | LLM方向 | 方向归因 | 模板方向 | LLM术语 | 模板术语 | LLM未溯源价位 | 状态 |",
        "|---|---|---:|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        title = (row.get("title") or "").replace("|", "/")
        llm_score = row.get("llm_score") or {}
        baseline = row.get("baseline_score") or {}
        status = row.get("status", "")
        md.append(
            f"| {row['date']} | {title} | {llm_score.get('direction', '-')} | "
            f"{llm_score.get('direction_attribution', '-')} | {baseline.get('direction', '-')} | {llm_score.get('term_overlap', '-')} | "
            f"{baseline.get('term_overlap', '-')} | {llm_score.get('unsourced_prices', '-')} | {status} |"
        )
    md.extend(["", "## 样本详情"])
    for row in rows:
        md.extend([
            "",
            f"### {row['date']} {row.get('title', '')}",
            "",
            f"- 状态: {row.get('status')}",
            f"- 真人倾向: {text_bias(row.get('human_text', ''))}",
            f"- 客观活跃买卖点: `{row.get('objective_active_buy_sell')}`",
            f"- 模板评分: `{row.get('baseline_score')}`",
            f"- LLM评分: `{row.get('llm_score')}`",
        ])
        if row.get("error"):
            md.append(f"- 错误: `{row['error']}`")
        if row.get("llm_text"):
            md.extend(["", "**LLM 输出摘录**", "", row["llm_text"][:1600]])
        else:
            md.extend(["", "**提示**", "", f"本行未调用 DeepSeek；请填写 `{CONFIG_FILE}` 或设置 `DEEPSEEK_API_KEY` 后去掉 `--dry-run` 重跑。"])
    report_path.write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run true LLM evaluation for chan-pan-analysis skill.")
    parser.add_argument("--start-date", default="2025-06-26", help="held-out start date")
    parser.add_argument("--limit", type=int, default=10, help="sample size; <=0 means all eligible records")
    parser.add_argument("--dates", nargs="*", default=None, help="specific dates to evaluate, e.g. 2025-07-29")
    parser.add_argument("--seed", type=int, default=20260617)
    parser.add_argument("--model", default=None, choices=sorted(ALLOWED_DEEPSEEK_MODELS),
                        help="DeepSeek model; default from config/env/deepseek-v4-flash")
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--dry-run", action="store_true", help="write prompts/tasks without calling DeepSeek")
    parser.add_argument("--out-jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--out-report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--tasks-jsonl", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--reuse-jsonl", type=Path, default=None,
                        help="reuse existing LLM outputs and rescore without calling DeepSeek")
    args = parser.parse_args()
    llm_config = load_llm_config()
    model = args.model or llm_config["model"]
    base_url = llm_config["base_url"]
    api_key = llm_config["api_key"]

    if args.reuse_jsonl:
        rows = []
        for line in args.reuse_jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            result = row.get("objective") or {}
            human = row.get("human_text", "")
            baseline_text = row.get("baseline_text") or render_template_baseline(result)
            row["baseline_text"] = baseline_text
            row["baseline_score"] = score_generated(baseline_text, human, result)
            if row.get("llm_text"):
                row["llm_score"] = score_generated(row["llm_text"], human, result)
                row["status"] = "ok"
            rows.append(row)
        args.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.out_jsonl.open("w", encoding="utf-8") as result_fh:
            for row in rows:
                result_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        write_markdown_report(rows, args.out_report, dry_run=not any(r.get("llm_text") for r in rows))
        print(args.out_report)
        print(args.out_jsonl)
        return

    records = load_eval_records(args.start_date)
    daily_dates = load_daily_dates()
    eligible = [r for r in records if r.get("date") in daily_dates]
    if args.dates:
        wanted = set(args.dates)
        eligible = [r for r in eligible if r.get("date") in wanted]
    eligible.sort(key=lambda r: r["date"])
    if not args.dates and args.limit > 0 and len(eligible) > args.limit:
        eligible = sorted(random.Random(args.seed).sample(eligible, args.limit), key=lambda r: r["date"])

    args.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with args.out_jsonl.open("w", encoding="utf-8") as result_fh, args.tasks_jsonl.open("w", encoding="utf-8") as task_fh:
        for idx, record in enumerate(eligible, 1):
            date = record["date"]
            result = run_analyzer(date)
            prompt = build_prompt(record, result)
            task_fh.write(json.dumps({"date": date, "prompt": prompt}, ensure_ascii=False) + "\n")
            baseline_text = render_template_baseline(result)
            baseline_score = score_generated(baseline_text, record.get("text", ""), result)
            row: dict[str, Any] = {
                "date": date,
                "title": record.get("article_title") or record.get("doc_title"),
                "human_text": record.get("text", ""),
                "objective": result,
                "objective_active_buy_sell": sorted(active_buy_sell_terms(result)),
                "baseline_text": baseline_text,
                "baseline_score": baseline_score,
                "llm_text": "",
                "llm_score": {},
                "status": "dry_run" if args.dry_run else "pending",
                "error": "",
            }
            if not args.dry_run:
                try:
                    row["llm_text"] = call_deepseek(prompt, api_key, base_url, model, args.max_tokens, args.temperature)
                    row["llm_score"] = score_generated(row["llm_text"], record.get("text", ""), result)
                    row["status"] = "ok"
                    time.sleep(0.3)
                except Exception as exc:  # noqa: BLE001 - CLI report should capture provider errors.
                    row["status"] = "error"
                    row["error"] = str(exc)
            rows.append(row)
            result_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{idx}/{len(eligible)}] {date} {row['status']}")

    write_markdown_report(rows, args.out_report, dry_run=args.dry_run or not any(r.get("llm_text") for r in rows))
    print(args.out_report)
    print(args.out_jsonl)
    print(args.tasks_jsonl)


if __name__ == "__main__":
    main()
