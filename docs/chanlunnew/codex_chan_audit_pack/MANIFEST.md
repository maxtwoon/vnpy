# 文件清单

- `README_FOR_CODEX.md`：使用说明。
- `records/conversation_record.md`：本次多轮审计交互记录摘要。
- `records/audit_claims_to_verify.md`：Codex 需要逐项复核的断言清单。
- `records/codex_prompt.md`：可直接复制给 Codex CLI 的任务提示。
- `payload/files_2_original.zip`：用户最后上传的原始包。
- `payload/chan_system_v1.0.2.zip`：从原始包中提取出的系统包。
- `payload/chan_system_v1.0.2_extracted/`：已解压代码，便于 Codex 直接审计。
- `scripts/verify_static_claims.py`：静态验证脚本，不依赖 `czsc`。
- `scripts/verify_runtime_with_czsc.py`：运行时验证脚本，需安装 `czsc`。
- `scripts/verify_pypi_versions.py`：可联网时验证 PyPI 版本事实。
- `scripts/run_all.sh`：一键执行脚本。
- `expected_outputs/`：当前沙箱中运行脚本的示例输出。注意当前沙箱无 `czsc` 且无法联网，因此 runtime 与 PyPI 验证会提示本地重跑。
