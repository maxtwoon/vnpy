# SimNow Connection Probe

This probe checks whether the local VeighNa runtime can connect to a SimNow CTP
environment. It is intentionally read-only: it never sends orders.

## What You Need To Provide

Create a private config file from:

```text
examples/czsc_strategy/diagnostics/simnow_connection_config.example.json
```

Recommended private file:

```text
examples/czsc_strategy/diagnostics/simnow_connection_config.json
```

Required fields:

- `用户名`: SimNow investor/account id
- `密码`: SimNow password
- `经纪商代码`: SimNow commonly uses `9999`
- `交易服务器`: CTP trading front, default template uses `tcp://182.254.243.31:30003`
- `行情服务器`: CTP market data front, default template uses `tcp://182.254.243.31:30013`
- `产品名称`: SimNow commonly uses `simnow_client_test`
- `授权编码`: SimNow commonly uses `0000000000000000`
- `柜台环境`: use `实盘` for SimNow CTP; `测试` is only for CTP penetration-test environments
- `subscribe`: optional current real contracts to subscribe; use exchange symbols such as `CZCE`, `SHFE`, `DCE`, `INE`, `GFEX`

Do not use research continuous symbols such as `AP888` or `SC888` in `subscribe`;
use actual tradable contracts such as `ap610` or `sc2608`.

## SimNow Profiles

The config template includes common SimNow CTP profiles:

| profile | trade front | market front | note |
|---|---|---|---|
| `simnow_trade_time_current` | `tcp://182.254.243.31:30003` | `tcp://182.254.243.31:30013` | current trading-time simulation; use CTP gateway with `柜台环境=实盘` |
| `simnow_trade_time_group1` | `tcp://180.168.146.187:10201` | `tcp://180.168.146.187:10211` | trading-time simulation |
| `simnow_trade_time_group2` | `tcp://180.168.146.187:10202` | `tcp://180.168.146.187:10212` | trading-time simulation |
| `simnow_trade_time_group3` | `tcp://218.202.237.33:10203` | `tcp://218.202.237.33:10213` | trading-time simulation |
| `simnow_7x24` | `tcp://180.168.146.187:10130` | `tcp://180.168.146.187:10131` | connection/process testing |

Current default fields follow the provided SimNow information:

- AppID: `simnow_client_test`
- AuthCode: `0000000000000000`
- terminal authentication: enabled by default
- CTP gateway counter environment: `实盘`; selecting `测试` can cause `4040 decode err / 4097`
- service time: same as the production trading environment
- initial simulated capital: 20 million
- products: all futures across six exchanges; all SHFE/INE/CFFEX/GFEX options; partial CZCE/DCE options

## Install Dependency

This repository does not include the CTP gateway package. Install it in the
same Python environment before running the real probe:

```powershell
pip install vnpy_ctp
```

## Commands

Generate a private template:

```powershell
python examples\czsc_strategy\diagnostics\simnow_connection_probe.py `
  --write-example-config `
  --config examples\czsc_strategy\diagnostics\simnow_connection_config.json
```

Validate config and dependency without connecting:

```powershell
python examples\czsc_strategy\diagnostics\simnow_connection_probe.py `
  --config examples\czsc_strategy\diagnostics\simnow_connection_config.json `
  --dry-run
```

Run the real read-only connection probe:

```powershell
python examples\czsc_strategy\diagnostics\simnow_connection_probe.py `
  --config examples\czsc_strategy\diagnostics\simnow_connection_config.json `
  --timeout 60 `
  --out-json examples\czsc_strategy\diagnostics\simnow_connection_probe_report.json
```

Success means at least one log plus account, contract, or tick event was
observed before timeout.
