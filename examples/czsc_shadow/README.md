# CZSC 离线影子接入

此入口使用当前 `czsc-timing-engine` 的 `VnpyShadowAdapter` 和公共 `TimingEngine`，
把 VN.PY 一分钟 `BarData` 送入引擎，逐条保存其原始决策。仅做研究观察，
不启动 MainEngine、不连接网关、不读取账户、不下单，也不计算策略收益。

使用独立 `czsc` 运行环境；不要向 vnpy 核心环境混装 CZSC 依赖。

```powershell
C:/Python314/python.exe D:/repo/quant/scripts/runtime.py run czsc -- D:/repo/vnpy/examples/czsc_shadow/run.py --input D:/research-input/closed-bars.jsonl --config D:/repo/vnpy/examples/czsc_shadow/futures.toml --output D:/research-runs/new-shadow-run --symbol IF2501.CFFEX --snapshot-id <真实源快照编号> --bar-label open --as-of 2025-01-02T15:00:00+08:00
```

输入和输出路径是使用示例，需替换为实际文件及**不存在的新目录**。
输入为 UTF-8 JSONL，每行一根；以下只展示字段格式：

```json
{"symbol":"IF2501.CFFEX","datetime":"2025-01-02T09:30:00+08:00","interval":"1m","closed":true,"open_price":100,"high_price":101,"low_price":99,"close_price":100,"volume":1,"turnover":100,"open_interest":88}
```

必须提供来源已确认的时间标签和闭合状态，不能用 `closed:true` 或 `--bar-label`
替代源数据验证。未知成交额/OI 不补零；字段缺失或非有限值会失败。
合约代码必须与准入标的一致，不把连续合约改名为可交易月合约。
当前附带配置为中金所股指期货日盘、默认中性 passthrough；其他会话应显式提供
与源数据相符的引擎配置。复用既有配置与证据门，不新增方向性规则。

输入必须严格单调、无重复，规范闭合时间不得晚于 `--as-of`。
回放接收时间等于规范闭合时间；EOF 不伪造会话关闭事件。
生产配置保留 20,000 根 warmup，不足时如实输出 warming_up，决策文件可以为空。

输出：

- `decisions.jsonl`：原引擎决策，含可用时间、有效期、原因和身份。
- `manifest.json`、`config.json`：引擎实际运行身份及解析配置。
- `result.json`：输入/配置/适配器哈希、固定快照编号、处理数量、健康状态与失败原因。

失败返回非零，并保留已有部分输出和 failed 状态；重试使用新目录。
这是离线消费者接线；真实消费者连续影子运行、收益验证和交易接入仍是独立事项。

## 验证与复用

```powershell
C:/Python314/python.exe D:/repo/quant/scripts/runtime.py run czsc -- -m pytest D:/repo/vnpy/examples/czsc_shadow/test_shadow.py -q
```

7 项真实公共引擎/BarData 工程测试通过：非空决策的确定性回放、输入不变、重复、
未闭合、超出截止、错误合约、缺少成交额和输出防覆盖。测试用合成 2025 年数据，
临时配置仅为触发输出而缩短 warmup；不修改附带配置或原项目默认值，不证明信号有效。

复用选择：现有 `examples/vnpy_shadow_adapter.py` 已承担时间、准入、关闭与失效语义；
这里只增加 vnpy 仓库的文件入口与落盘。启动验证真实 CZSC 包与所选项目路径一致。
2026-09-30 已执行当前 doctor（CZSC 1.0.1）及 catalog（246 项），未改变上游实现。
