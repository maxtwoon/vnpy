"""
解盘语料清洗器 (Corpus Cleaner)
================================

扫描每日缠论解盘 Markdown 文件，清洗成结构化 JSONL，供后续
"信号 ↔ 解盘话术" 映射与 skill few-shot / 评估使用。

输入文件结构（每个 *.md）：
    # A股每日复盘 - YYYY-MM-DD
    > 日期: ...
    > 收录篇数: N
    > 文章标题: ...
    ## 第1篇: <title>
    ### Markdown 原文
    <正文>
    ### HTML 清洗文本
    <正文重复>
    ...footer / 免责声明

清洗策略：
    - 每篇优先取 "Markdown 原文"（结构更完整），与 "HTML 清洗文本" 去重。
    - 去图片、URL、公众号样板行、免责声明、合并脚本签名。
    - 4 空格段分隔 → 换行；去转义竖线、多余 # * 标记。
    - 抽取轻量信号：候选关键价位、买卖点/结构术语命中、情景树分支数。

输出：
    - <out>/corpus.jsonl        每篇一行记录
    - <out>/corpus_stats.json   语料统计（日期范围、术语/形态频次）
    - 终端打印摘要

用法：
    python corpus_cleaner.py --src D:\\repo\\outputs --out D:\\repo\\vnpy\\examples\\czsc_strategy\\skill_build\\corpus
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional


# ---- 纯噪声行：命中即整行丢弃（这些行不含正文结论）----
_DROP_LINE_SUBSTRINGS = [
    "主播", "神光弘缠", "在小说阅读器", "去阅读", "沉浸阅读",
    "投资谨慎", "仅供参考", "投资建议", "出售投资标的",
    "此文件由自动化脚本合并生成",
]

# ---- 尾部客套短语：就地删除（常和操作/结构结论同处最后一段，不能丢整行）----
_TAIL_PHRASE_RE = re.compile(
    r"(今天的解盘就到这里|今天就(谈|讲)到这里|今天就到这里|"
    r"我们晚间[《<][^》>]*[》>][^。！]*|《市场连线》[^。！]*|市场连线[^。！]*|"
    r"谢谢各位|谢谢大家|感谢(各位|大家)(收听|收看)?)[，。！、…\s]*"
)

# ---- 用于统计形态覆盖的缠论术语表 ----
_TERM_GROUPS: Dict[str, List[str]] = {
    "买卖点": ["一买", "二买", "三买", "一卖", "二卖", "三卖", "二三买", "二三卖"],
    "结构": ["中枢", "线段", "顶分型", "底分型", "分型", "背驰", "盘整", "趋势",
             "缺口", "离开段", "进入段", "走势类型", "中枢构建", "中枢扩展"],
    "强弱": ["强调整", "弱调整", "正常调整", "温和", "量能", "承接", "背驰"],
    "级别": ["1F", "5F", "30F", "日线", "周线", "1分钟", "5分钟", "30分钟", "月线"],
    "情景": ["第一种", "第二种", "第三种", "演绎", "推演"],
}

_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_URL_RE = re.compile(r"https?://\S+")
_ARTICLE_RE = re.compile(r"^##\s*第\s*(\d+)\s*篇\s*[:：]\s*(.*)$", re.MULTILINE)
_LEVEL_NUM_RE = re.compile(r"(?<!\d)([2-6]\d{3})(?:\.\d+)?(?!\d)")  # 候选指数点位 2000-6999


def _strip_inline(text: str) -> str:
    """行内清洗：去图片、URL、转义竖线、Markdown 标记符。"""
    text = _IMG_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = text.replace("\\|", " ").replace("|", " ")
    # 去掉行首的 markdown 标题井号与强调星号（保留文字）
    text = re.sub(r"[*#]+", "", text)
    return text


def _clean_body(raw: str) -> str:
    """正文清洗：拆段、去样板行、规整空白。"""
    raw = _strip_inline(raw)
    # 原文里用连续 4+ 空格当段落分隔，先换成换行
    raw = re.sub(r"[ 　]{4,}", "\n", raw)
    lines = []
    for ln in raw.splitlines():
        s = ln.strip()
        if not s:
            continue
        # 纯噪声行整行丢弃
        if any(b in s for b in _DROP_LINE_SUBSTRINGS):
            continue
        # 尾部客套短语就地删除（保留同段的结论文字）
        s = _TAIL_PHRASE_RE.sub("", s).strip(" ，。！、…")
        if not s or s in {"---"}:
            continue
        # 合并多余内部空格
        s = re.sub(r"[ 　]{2,}", " ", s)
        lines.append(s)
    # 去掉相邻重复行
    out: List[str] = []
    for s in lines:
        if not out or out[-1] != s:
            out.append(s)
    return "\n".join(out).strip()


def _extract_article_body(block: str) -> str:
    """从单篇 block 中优先取 'Markdown 原文'，否则取 'HTML 清洗文本'。"""
    md = re.search(r"###\s*Markdown\s*原文\s*\n(.*?)(?=\n###\s|\Z)", block, re.S)
    if md and md.group(1).strip():
        return md.group(1)
    html = re.search(r"###\s*HTML\s*清洗文本\s*\n(.*?)(?=\n###\s|\Z)", block, re.S)
    if html and html.group(1).strip():
        return html.group(1)
    # 没有分节：返回整个 block（去掉标题行）
    return re.sub(r"^##\s*第.*$", "", block, flags=re.MULTILINE)


def _front_matter(text: str, fallback_date: str) -> Dict[str, str]:
    def grab(label: str) -> Optional[str]:
        m = re.search(rf">\s*{label}\s*[:：]\s*(.+)", text)
        return m.group(1).strip() if m else None
    return {
        "date": grab("日期") or fallback_date,
        "n_articles": grab("收录篇数") or "",
        "doc_title": grab("文章标题") or "",
    }


def _term_hits(text: str) -> Dict[str, Dict[str, int]]:
    hits: Dict[str, Dict[str, int]] = {}
    for group, terms in _TERM_GROUPS.items():
        g: Dict[str, int] = {}
        for t in terms:
            c = text.count(t)
            if c:
                g[t] = c
        if g:
            hits[group] = g
    return hits


def _candidate_levels(text: str) -> List[str]:
    """抽取候选关键价位（去重、保序）。低保真，仅作映射阶段线索。"""
    seen = []
    for m in _LEVEL_NUM_RE.finditer(text):
        v = m.group(1)
        if v not in seen:
            seen.append(v)
    return seen[:20]


_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}


def _scenario_count(text: str) -> int:
    """估计情景分支数。覆盖多种表达：
    第X种/第X条、X种演绎/走势、一种是…另一种是、还有/另一种走势。
    """
    n = 0
    for m in re.finditer(r"第([一二三四五六])[种条]", text):
        n = max(n, _CN_NUM[m.group(1)])
    for m in re.finditer(r"([一两二三四五])种(?:演绎|走势|情况|可能|推演|理解)", text):
        n = max(n, _CN_NUM.get(m.group(1), 0))
    if re.search(r"一种(?:是|走势|可能).{0,80}?(?:另一种|另外一种|第二种|二种)", text):
        n = max(n, 2)
    if re.search(r"(?:还有|另)(?:外)?(?:一|另)?种(?:走势|演绎|情况|可能|理解)", text):
        n = max(n, 2)
    return n


_MARKET_REVIEW_MARKERS = [
    "指数缠论结构分析", "上证指数", "上证日线", "上证1分钟", "上证5分钟",
    "大盘", "今日，上证", "日线走势结构", "1分钟走势结构", "5分钟走势结构",
]

_THEORY_TEACHING_MARKERS = [
    "教你炒股票", "摘录原文", "学习小结", "交易体系", "登记编号",
    "分型、笔、线段", "再说说分型", "缠论原文", "课程", "定义",
]


def _article_type(title: str, text: str) -> str:
    """粗分类语料用途，避免把理论教学文混入行情复盘评估。"""
    combined = f"{title}\n{text}"
    market_score = sum(1 for marker in _MARKET_REVIEW_MARKERS if marker in combined)
    theory_score = sum(1 for marker in _THEORY_TEACHING_MARKERS if marker in combined)
    if market_score and theory_score:
        return "mixed"
    if theory_score >= 1 and market_score == 0:
        return "theory_teaching"
    if market_score >= 1:
        return "market_review"
    return "unknown"


def clean_file(path: Path) -> List[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    fallback_date = path.stem  # 文件名即日期
    fm = _front_matter(text, fallback_date)

    records: List[dict] = []
    matches = list(_ARTICLE_RE.finditer(text))
    if not matches:
        # 没有 "第N篇" 分节：整文件当一篇
        body = _clean_body(_extract_article_body(text))
        if body:
            records.append(_make_record(fm, 1, fm["doc_title"], body, path))
        return records

    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        title = m.group(2).strip()
        body = _clean_body(_extract_article_body(block))
        if body:
            records.append(_make_record(fm, int(m.group(1)), title, body, path))
    return records


def _make_record(fm: dict, idx: int, title: str, body: str, path: Path) -> dict:
    return {
        "date": fm["date"],
        "doc_title": fm["doc_title"],
        "article_idx": idx,
        "article_title": title,
        "article_type": _article_type(title or fm["doc_title"], body),
        "text": body,
        "char_len": len(body),
        "n_scenarios": _scenario_count(body),
        "candidate_levels": _candidate_levels(body),
        "term_hits": _term_hits(body),
        "source_file": path.name,
    }


def main():
    ap = argparse.ArgumentParser(description="解盘语料清洗器")
    ap.add_argument("--src", default=os.getenv("CHAN_REVIEW_CORPUS_DIR", r"D:\repo\outputs"),
                    help="语料目录（默认环境变量 CHAN_REVIEW_CORPUS_DIR 或 D:\\repo\\outputs）")
    ap.add_argument("--out", default="corpus", help="输出目录")
    ap.add_argument("--min-chars", type=int, default=80,
                    help="正文最少字数，低于则跳过（过滤空/异常篇）")
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    files = sorted(src.glob("*.md"))
    if not files:
        print(f"未找到 md 文件: {src}")
        return

    all_records: List[dict] = []
    skipped = 0
    for f in files:
        for rec in clean_file(f):
            if rec["char_len"] < args.min_chars:
                skipped += 1
                continue
            all_records.append(rec)

    # 写 JSONL
    jsonl_path = out / "corpus.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for rec in all_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 统计
    dates = sorted({r["date"] for r in all_records})
    term_total: Counter = Counter()
    for r in all_records:
        for group, terms in r["term_hits"].items():
            for t, c in terms.items():
                term_total[t] += c
    scenario_dist = Counter(r["n_scenarios"] for r in all_records)
    type_dist = Counter(r.get("article_type", "unknown") for r in all_records)

    stats = {
        "n_files": len(files),
        "n_articles": len(all_records),
        "skipped_short": skipped,
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "term_frequency": dict(term_total.most_common()),
        "scenario_count_distribution": dict(sorted(scenario_dist.items())),
        "article_type_distribution": dict(sorted(type_dist.items())),
        "avg_char_len": round(sum(r["char_len"] for r in all_records) / len(all_records), 1) if all_records else 0,
    }
    (out / "corpus_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 终端摘要
    print(f"清洗完成: {len(files)} 文件 → {len(all_records)} 篇 (跳过过短 {skipped})")
    print(f"日期范围: {stats['date_min']} ~ {stats['date_max']}")
    print(f"平均字数: {stats['avg_char_len']}")
    print(f"情景分支分布(篇数): {stats['scenario_count_distribution']}")
    print(f"文章类型分布(篇数): {stats['article_type_distribution']}")
    print("术语高频 TOP20:")
    for t, c in term_total.most_common(20):
        print(f"  {t}: {c}")
    print(f"\n输出: {jsonl_path}")
    print(f"      {out / 'corpus_stats.json'}")


if __name__ == "__main__":
    main()
