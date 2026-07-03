# 可直接给 Codex CLI 的提示词

你现在是本地代码审计助手。请读取当前目录下的 `README_FOR_CODEX.md`、`records/conversation_record.md` 和 `records/audit_claims_to_verify.md`，然后审计 `payload/chan_system_v1.0.2_extracted`。

任务目标：复核 ChatGPT 前面关于缠论交易系统 v1.0.2 的审计结论，特别是 ChatGPT 云端环境因为没有安装 `czsc` 而无法验证的运行问题。

请按以下步骤执行：

1. 先运行：

```bash
bash scripts/run_all.sh
```

2. 如果运行时检查提示没有安装 `czsc`，请创建临时虚拟环境并执行：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python scripts/verify_runtime_with_czsc.py --install
```

3. 可联网时再运行：

```bash
python scripts/verify_pypi_versions.py
```

4. 按 `records/audit_claims_to_verify.md` 中 A-D 四组断言逐项给出：确认 / 反驳 / 无法判断。

5. 最后输出一份 Markdown 审计报告，结构为：

```markdown
# Codex 复核报告

## 总结

## 环境信息

## 逐项断言复核

| 编号 | 结论 | 证据 | 备注 |
|---|---|---|---|

## 运行测试结果

## 对 ChatGPT 审计结论的反驳或确认

## 下一版建议
```

注意：不要只看文档声明，要以代码、命令输出和本地运行结果为准。
