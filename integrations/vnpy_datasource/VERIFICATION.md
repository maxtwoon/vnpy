# 接入验证记录

核对时间：2026-09-15晚至2026-09-16凌晨，Asia/Shanghai。

## 本机交付

- Studio Python3.13.8已安装本地`vnpy_datasource==0.1.0`，`get_datafeed()`实际返回`DataSourceDatafeed`且本地初始化成功。
- 查询实际经过`dataSource/registry/ds.py run`进入当前维护Python3.14.7。
- 台账读取时SHA-256：`7442f1416a710a7d7649db8077c6358586c08d9b037554d12f6657b062ad568a`。
- 原数据源仓库和凭证未修改。vnpy核心和旧缠论代码未修改。
- Studio既有发行包版本无变动；补装研究和验证依赖后`pip check`通过。

## 真实取数与消费

首轮固定窗口为2026-09-01至2026-09-14；五分钟为9月14日。

| 验证 | 结果 |
|---|---|
| 新浪600519原价日线 | 10行 |
| BaoStock600519前复权日线 | 10行 |
| 新浪159915 ETF日线 | 10行 |
| 新浪上证指数日线 | 10行 |
| 新浪交易日历 | 10个交易日 |
| 腾讯股票+ETF批量报价 | 2行 |
| BaoStock159915五分钟 | 48根，开始时间口径 |
| BaoStock600519 2025Q4盈利表 | 1行 |
| Tushare既有网关股票原价日线 | 10行 |
| 雪球159915报价 | 1行，字段齐全 |
| 妙想明确关键词选股 | 10行，partial=false |
| Yahoo159915原价日线补测 | 失败；SDK抛YFPricesMissingError，尚未进入本地parser，保留失败、不判为数据可用 |
| ETF写入独立SQLite | 10行SQL读回；原生vnpy_sqlite再读取数量／收盘价完全一致 |
| ETF写入Alpha Parquet | 10行Polars读回；原生AlphaLab再读取数量／收盘价完全一致 |
| CTA标准load_bar | 真实Datafeed返回10根；使用无Gateway的最小main_engine适配对象，强制禁止数据库回退 |
| 最小研究脚本 | Datafeed读取43根ETF日线，另取得真实交易日历 |

原始返回和汇总在本机：

`D:\repo\vnpy\integrations\vnpy_datasource\output\verification-20260915-235250\`

其中`summary.json`为首轮9项；`native-readback.json`为原生读取及CTA消费；`extra-xueqiu.json`与`extra-miaoxiang.json`为补充源实测；`extra-yahoo-daily.json`保留Yahoo补测失败。对该失败仅追加一次3.7秒底层诊断，固定分类为`upstream_prices_missing`；请求映射正确，未发现本地解析问题，也没有修改源台账状态。GUI／策略查询回执另存于`.vntrader/datasource_receipts/`。

## 真实数据发现与处理

1. 9月11日159915：Sina与BaoStock OHLC／成交量一致，成交量1,905,297,197份；成交额分别6,320,257,883和6,320,257,882.811元，属于显示精度差。Tencent量相差3份，为显示舍入。
2. Tencent上证指数原生数量579,123,145，对应Sina57,912,314,500股；适配器需乘100。
3. AKShare1.18.94对`sz000`股票漏做手转股：平安银行Tencent原数832,461、BaoStock83,246,084股。修正仅针对已验证的SDK版本与代码类型，不对未来版本无条件乘100。
4. Yahoo ETF159915的9月14日一分钟返回329行，其中89行位于午休时段，且一分钟成交量合计4,047,127,126份，而新浪当日日线为1,185,247,814份。当前适配器拒绝Yahoo A股／ETF分钟行情，保留取样文件`yahoo-minute-investigation.json`作为失败调查数据。该文件早期的`status=ok`只表示网络调用成功，不是数据验收通过。
5. 一分钟`history`最终会明确返回`unsupported`：BaoStock无1分钟；Tencent只给分时点；PyTDX最新能力UNKNOWN；miniQMT尚未就绪；Yahoo分钟质量不合格。没有填造一分钟数据。

## 工程验证

- 81项针对性离线测试通过：状态／时效过滤、语义匹配、凭证保护、单位、时间、重复冲突、超时清理、来源后备、存储与CLI。
- 独立复核发现的UTC日期边界和超时清理异常问题均已修正并加用例。
- Ruff检查通过；保留一个现有pytz的弃用提示。
- 根目录sync_check通过，handoff工具已将本次任务推进至done；38个本地文档链接检查有效。

## 验证边界

不是54个配方全部联网实测；实际联网覆盖以上样本。接口就绪、源端资料可用、整个市场覆盖、历史PIT和策略收益是不同结论。未进行策略收益回测、交易连接、下单或Trader GUI操作。AlphaLab导入和读取已通，完整因子／模型／回测流程尚未运行。

## 2026-09-16：`--target store` 不可变研究库目标

新增存储目标`store`：下载结果写入 `D:\repo\vnpy\integrations\vnpy_researchstore` 的不可变research_store。原始结果JSON逐字节存入库内`captures/`并以SHA-256登记为导入资产；缺失成交额保持真实NULL；发布后冻结快照并用SnapshotReader真实读回逐行比对（非mock）。数据源回执在库内`reports/`，库根不写`datasource-manifest.json`。改动仅限 `vnpy_datasource/storage.py`、`vnpy_datasource/cli.py`（choices加一项）、新增 `tests/test_storage_store.py` 及本节文档；未改动vnpy_researchstore任何文件。

实际执行（工作目录 `D:\repo\vnpy\integrations\vnpy_datasource`）：

| 命令 | 结果 |
|---|---|
| `D:/repo/vnpy/integrations/vnpy_researchstore/.venv/Scripts/python.exe -m pytest tests -q` | **87 passed**（81既有 + 6新增store用例；含真实快照读回、NULL成交额读回为NULL、非ok拒绝、重复导入幂等且batch_id不变、非托管目录拒绝、分钟缺time_label拒绝） |
| `D:/veighna_studio/python.exe -m pytest tests -q` | 81 passed, 1 skipped（Studio缺duckdb，store整组干净跳过，不红） |
| `D:/veighna_studio/python.exe -m ruff check vnpy_datasource tests` | All checks passed |
| 额外手动端到端：合成两条日线（一条turnover=None）经`save_history(..., "store", ...)`写入临时库 | status ok，verified_rows=2，返回JSON可被`json.dumps(allow_nan=False)`序列化（CLI兼容） |

store目标的测试只能用researchstore的`.venv`解释器真实运行（该环境带research_store/pyarrow/duckdb/zstandard且vnpy_datasource可导入）。NOT_RUN：`download --target store` 的真实联网下载（本次未做任何网络取数）；分钟级写入仅有拒绝路径用例，真实分钟收据未跑。

## 2026-09-21：本地回测库接入

- Studio Python 3.13 补装 `duckdb 1.5.5`、`pyarrow 25.0.1`；`warehouse.query.Snapshot` 在 3.13 下直接可用（原库在 3.14 环境建立）。
- `WarehouseReader` 实测：159915.SZSE 日线 2026-09-01→09-18 14 行（RQ 归档 + 新浪段）；510050.SSE 1 分钟 2026-09-11 240 根，标签 09:30→14:59（已由结束标签转开始标签）；600519.SSE 1 分钟返回 `no_data: dataset_not_in_warehouse:bars_stock_1m`；399001.SZSE 日线 2026-08-25→09-18 19 行，`missing_fields` 含 `volume`；000001.SZSE 60 分钟 12 根（开盘啦导入）。
- `load-warehouse` 4 只（159915/510300/600519/399001）2024-01-01→2026-09-18 各 659 行写入 `research_data/wh_etf_sqlite`，SQLite 逐行读回一致，manifest/receipts 记 `snapshot_id=20260920T173637Z-c6cc6b2e`。
- `examples/warehouse_backtest.py`：`get_database()` 读回 659 根，`BacktestingEngine` + DoubleMaStrategy 完整跑通（652 天、47 笔），仅验证链路不评价策略。
- `get_datafeed()` 实测：510300 日线 / 510050 1 分钟由本地库返回（约 1 秒，`source=warehouse`，有回执）；600519 1 分钟本地无 → 打印"改走在线源"后按原逻辑失败（`unsupported`）。
- 测试：插件 92 项通过（新增 `tests/test_warehouse.py` 4 项、Datafeed 本地优先/回退 1 项；原在线日期转换测试改为显式关闭本地优先）。
- 未改动 vnpy 核心、全局 `vt_setting.json`（新键均有默认值）与 dataSource 仓库。

