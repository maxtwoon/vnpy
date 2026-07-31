<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

# czsc 1.0.0rc8 理论断言探针报告

- 生成时间：2026-07-29 11:22:11
- Python：3.14.4（C:\Python314\python.exe）
- czsc：1.0.0rc8（C:\Python314\Lib\site-packages\czsc）
- 数据：`czsc.mock.generate_symbol_kines("MOCK000", "30分钟", sdt=20200101, edt=20210601, seed=42)` 合成 K 线，不触网
- 性质：只读探针；不发委托、不调交易接口、不改任何策略参数

## 结论速览

- 断言 A（ZS 默认是笔中枢）：**证实（ZS 仅能由 BI 列表构造，构成元素全部为笔；官方类型存根 `ZS.bis: list[BI]`）**
- 断言 B（三类买卖点 = czsc 内置倒1/倒2 多笔形态信号）：**证伪（rc8 未内置该类信号函数）**

## 断言 A 细节：ZS 构成

- 合成 K 线 5180 根 → `CZSC(bars)`；`bi_list` 保留 50 根（`max_bi_num=50`，rc8 默认只保留最近 N 笔），`finished_bis` 50 根，元素类型 ['BI']
- **`CZSC` 本体无 `zs_list` 属性**（hasattr = False）：rc8 的 CZSC 只完成包含处理、分型与笔识别，**不自动构建中枢**；本项目自研 `build_zhongshu_from_bis()` 正是填补这一空白的必要实现，而非重复造轮子
- `CZSC.signals` 实例属性存在，为空 `OrderedDict`（长度 0）：仅是信号缓存槽，需外部信号函数写入
- 用前 5 根已完成笔直接构造 `ZS(bis=...)`：

| 输入元素类型 | zg | zd | gg | dd | zz | sdir | edir | 构成元素类型 |
|---|---|---|---|---|---|---|---|---|
| ['BI'] | 84.33 | 79.97 | 87.02 | 79.25 | 82.15 | 向上 | 向上 | ['BI'] |

- 官方类型存根（`_native/__init__.pyi`）：`ZS.bis: list[BI]` ——「获取构成中枢的笔列表」
- ZS 附带 `sdir`（中枢第一笔方向）/ `edir`（中枢倒一笔方向）属性：描述的是中枢**内部**首/末笔方向，与书上「中枢方向 = 进入段方向」口径不同，不可直接当作书义中枢方向使用

## 断言 B 细节：内置信号库

- `czsc.signals` 子模块存在：**False**（rc8 无此模块；`generate_czsc_signals(bars, signals_config)` 仅按用户自备 config 调用信号函数，库本身不附带任何形态信号实现）
- 关键词全包扫描（.py/.pyi）：

| 关键词 | 命中文件 |
|---|---|
| 三买 | （无） |
| 三卖 | （无） |
| 五笔 | （无） |
| 七笔 | （无） |
| 九笔 | （无） |

> 注：`aphorism.py`（语录文本）、`fsa/`（飞书集成）中的「倒」「笔」命中与形态信号无关；`_native/__init__.pyi` 中「中枢倒一笔方向」是 ZS.edir 的字段文档，非信号。

## 对项目的影响（回写 docs/theory_code_crosscheck.md §8）

1. 断言 A 证实后：书摘立场成立——可获取的中枢均为笔中枢（rc8 甚至不自动构建中枢，ZS 类仅接受 BI 列表）。报告层标注「笔中枢」的 P0 整改前提成立。
2. 断言 B 证伪后：书摘中「读 czsc 倒1/倒2 信号定性三类买卖点」的路径在 rc8 **不可用**（该 API 形态存在于旧版 czsc）。项目自研三阶段状态机（`signals.py` / `sell_signals.py`）是当前唯一实现；将来若需 czsc 原生形态信号做交叉验证，须自行移植旧版信号函数或放弃该路线。
3. 附带发现：`CZSC.max_bi_num` 默认限制笔缓存长度（本探针为 50），长序列分析时若依赖 `bi_list` 需留意截断；`finished_bis` 同受此限。
