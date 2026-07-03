# Codex CLI 验证包：缠论交易系统 v1.0.2 审计复核

本压缩包用于让本地 Codex CLI 复核前面 ChatGPT 审计中“当前环境无法验证/需要本地验证”的问题，尤其是：

1. `czsc` 真实安装版本、真实 API 字段与文档声明是否一致；
2. `chan_system_v1.0.2` 的 `tests/test_basic.py` 是否真的能跑出 `7 passed, 0 failed`；
3. `czsc_adapter.py`、`bsp_state_machine.py`、`xd_segment.py` 的静态问题是否存在；
4. 审计中指出的缺口是否属实：`new_bars` 未完整输出、`xd_zs=[]`、无多级别模块、状态机无持仓上下文、三买/二买逻辑简化、白名单测试不完整等。

## 目录说明

```text
payload/
  files_2_original.zip                  # 用户上传的原始 files(2).zip
  chan_system_v1.0.2.zip                # 从 files(2).zip 中提取出的系统包
  chan_system_v1.0.2_extracted/         # 已解压版本，便于直接阅读

records/
  conversation_record.md                # 上面交互的关键审计记录整理
  audit_claims_to_verify.md             # 需要 Codex 逐项验证的审计断言
  codex_prompt.md                       # 可直接复制给 Codex CLI 的任务提示词

scripts/
  verify_static_claims.py               # 不依赖 czsc 的静态验证脚本
  verify_runtime_with_czsc.py           # 依赖 czsc 的运行验证脚本，可选自动安装
  verify_pypi_versions.py               # 可联网时验证 PyPI 上 czsc 版本事实
  run_all.sh                            # 一键运行静态检查 + 尝试运行时检查
```

## 推荐运行方式

安装最新预发布版 `czsc==1.0.0rc8` 并执行运行时验证：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/update_czsc_latest.ps1
```

Linux / macOS / Git Bash：

```bash
bash scripts/update_czsc_latest.sh
```

在本包根目录运行：

```bash
bash scripts/run_all.sh
```

如果本地没有安装 `czsc`，并且你允许创建/修改当前 Python 环境，可以运行：

```bash
python scripts/verify_runtime_with_czsc.py --install
```

更推荐在一个临时虚拟环境中执行：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python scripts/verify_runtime_with_czsc.py --install
```

## 给 Codex CLI 的最短指令

```text
请读取 README_FOR_CODEX.md 和 records/codex_prompt.md，执行 scripts/run_all.sh。若 runtime 检查因为缺少 czsc 失败，请创建临时 venv 并运行 python scripts/verify_runtime_with_czsc.py --install。最后按 records/audit_claims_to_verify.md 逐项给出“确认/反驳/无法判断”的复核报告。
```
