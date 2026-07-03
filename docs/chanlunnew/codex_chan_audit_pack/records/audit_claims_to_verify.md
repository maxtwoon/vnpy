# 需要 Codex 逐项验证的审计断言

请对以下断言逐项给出：确认 / 反驳 / 无法判断，并说明证据路径、命令输出或代码位置。

## A. 运行环境与 czsc API

A1. 使用最新预发布版 `czsc==1.0.0rc8` 可运行本项目。

A2. `czsc==1.0.0rc8` 的 `CZSC` 对象有 `bars_raw`、`bars_ubi`、`fx_list`、`bi_list`、`signals`、`zs_list` 等字段。

A3. `czsc==1.0.0rc8` 中直接将 `bi.direction` 与 `"向上"/"向下"` 比较是否存在风险；是否仍需要 `str()` 或标准化函数。

## B. v1.0.2 可运行性

B1. 三个核心文件 `czsc_adapter.py`、`bsp_state_machine.py`、`xd_segment.py` 语法编译通过。

B2. 在本地安装 `czsc==1.0.0rc8` 后，`payload/chan_system_v1.0.2_extracted/tests/test_basic.py` 是否真的输出 `7 passed, 0 failed`。

B3. `czsc_adapter.analyze()` 是否能用 `czsc.mock.generate_symbol_kines` 生成 mock 数据并输出可 JSON 序列化结果。

## C. 上次审计指出的静态缺口

C1. `czsc_adapter.py` 顶层输出包含 `xd`、`xd_zs`，但它们固定为空列表，未真正接入线段中枢。

C2. `FIELD_WHITELIST` 没有覆盖 `xd`、`xd_zs`。

C3. `tests/test_basic.py` 只检查了 `bi` 字段未超白名单，没有全量校验 top-level keys、meta、fx、bi_zs、beichi、signals、xd、xd_zs。

C4. 当前版本没有完整输出 `new_bars` 列表；只有 `n_new_bars` 统计。

C5. 当前版本没有 `multi_level_analyzer.py` 或等价多级别联立模块。

C6. `bsp_state_machine.decide()` 函数签名没有 `position`、`prior_bsp` 等交易上下文参数。

C7. 三买逻辑仍然是简化条件，近似为“最后一笔向上且 low > ZG”，没有完整拆出离开中枢、等待回抽、回抽确认、不回中枢、触发、失效。

C8. 二买逻辑仍然是简化条件，没有依赖历史一买锚点或 `prior_bsp`。

C9. `compute_beichi()` 只会产生 `status="suspected"` 或 `"none"`，当前代码没有把背驰升级为 `confirmed` 的多级别区间套模块，因此 `confirmed` 在运行流程中基本不可达。

C10. `xd_segment.py` 虽有代码，但文件头明确声明“未通过正确性验证、默认不启用、不计入 v1.0.x 可验收交付”。

## D. 包结构问题

D1. README 标题/目录版本号仍可能是 v1.0，而不是 v1.0.2。

D2. 文档中文文件名在不同系统解压可能出现乱码风险；建议后续改英文文件名。

D3. `files(2).zip` 根目录存在重复的 `xd_segment.py`、`bsp_state_machine.py`，同时内嵌 zip 中也有对应文件。

## 输出要求

请最终生成一份 Markdown 报告，至少包含：

1. 每条断言的判定；
2. 用到的命令；
3. 关键证据片段；
4. 若反驳 ChatGPT 审计，请明确指出反驳依据；
5. 若确认缺口，请给出下一版修改建议。
