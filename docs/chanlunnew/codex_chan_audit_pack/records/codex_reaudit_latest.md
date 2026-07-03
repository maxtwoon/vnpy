# Codex 复核报告（czsc 1.0.0rc8）

复核日期：2026-06-15

## 总结

- 使用环境：Python 3.12.13，`czsc==1.0.0rc8`。
- `verify_runtime_with_czsc.py` 成功完成。
- `tests/test_basic.py` 实测输出 `7 passed, 0 failed`。
- `czsc_adapter.analyze()` 成功生成可 JSON 序列化结果。
- rc8 与当前适配层基础兼容，没有发现运行时 API 崩溃。
- A2 被运行结果反驳：`czsc==1.0.0rc8` 没有 `CZSC.zs_list`。
- C、D 组静态缺口全部仍然成立。

## 环境信息

```text
Python: 3.12.13
Python executable: .venv-czsc-rc8/Scripts/python.exe
czsc: 1.0.0rc8
```

## 逐项断言复核

| 编号 | 结论 | 证据 |
|---|---|---|
| A1 | 确认 | `czsc==1.0.0rc8` 已安装，并成功运行项目 runtime 与捆绑测试。 |
| A2 | 反驳 | 实测 `bars_raw/bars_ubi/fx_list/bi_list/signals` 均存在，但 `has_zs_list=false`。 |
| A3 | 确认 | `bi.direction` 类型为 `Direction`；直接与 `"向上"`、`"向下"` 比较均为 `false`。 |
| B1 | 确认 | 三个核心文件 AST 解析通过。 |
| B2 | 确认 | 捆绑测试实测输出 `7 passed, 0 failed`，返回码为 0。 |
| B3 | 确认 | runtime 成功调用 mock 数据和 `analyze()`；输出文件可由 `json.loads` 读取。 |
| C1 | 确认 | runtime 输出中 `xd=[]`、`xd_zs=[]`。 |
| C2 | 确认 | `FIELD_WHITELIST` 未包含 `xd`、`xd_zs`。 |
| C3 | 确认 | 测试仅对白名单中的 `bi` 字段做超集检查。 |
| C4 | 确认 | runtime 报告显示 `has_new_bars_key=false`，仅有 `n_new_bars`。 |
| C5 | 确认 | 未发现 `multi_level_analyzer.py` 或等价实现。 |
| C6 | 确认 | `decide` 参数仅为 `adapter_json, level_label`。 |
| C7 | 确认 | 三买仍由 `last_dir == "向上" and last_bi["low"] > last_zs["zg"]` 简化触发。 |
| C8 | 确认 | 二买逻辑未依赖历史一买锚点或 `prior_bsp`。 |
| C9 | 确认 | `compute_beichi()` 只赋值 `suspected` 或 `none`，没有 confirmed 升级模块。 |
| C10 | 确认 | `xd_segment.py` 明确声明实验性、未通过验证、默认不启用。 |
| D1 | 确认 | README 首行仍为 `# 缠论分析交易系统 v1.0`。 |
| D2 | 确认 | 当前解压目录中的中文文档文件名已出现乱码。 |
| D3 | 确认 | 原始 zip 根目录和内嵌 zip 均包含 `xd_segment.py`、`bsp_state_machine.py`。 |

## 关键运行结果

```text
czsc_version: 1.0.0rc8
结果: 7 passed, 0 failed

has_bars_raw: true
has_bars_ubi: true
has_fx_list: true
has_bi_list: true
has_signals: true
has_zs_list: false
bi_direction_type: Direction
has_new_bars_key: false
```

## rc8 API 补充结果

以下 `BI` 字段在 rc8 中均存在：

```text
power_price, power_volume, length, slope, change,
power_snr, SNR, acceleration, rsq
```

## 结论

v1.0.2 在 Python 3.12.13 与 `czsc==1.0.0rc8` 环境下具备基础可运行性。原先无法验证的 B2、B3 已确认通过。原审计指出的功能完整性、状态机、多级别联立、线段中枢、完整字段白名单与包结构问题仍然成立。
