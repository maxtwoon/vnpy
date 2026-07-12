# AGENTS.md — VeighNa Quantitative Trading Framework

> This file is written for AI coding agents who need to understand and work on the VeighNa (`vnpy`) codebase. The project user-facing documentation (`README.md`, `docs/`, `CHANGELOG.md`) is primarily in Chinese, but code comments, docstrings, and symbol names are in English. This document is therefore written in English.

---

## Project Overview

VeighNa (`vnpy`) is an open-source, Python-based quantitative trading system development framework. It provides an event-driven architecture for building trading applications that connect to multiple broker gateways, consume market data feeds, run strategy algorithms, and manage risk.

* **Repository**: https://github.com/vnpy/vnpy/
* **Homepage / Docs**: https://www.vnpy.com / https://www.vnpy.com/docs
* **License**: MIT
* **Current version**: `4.4.0` (defined in `vnpy/__init__.py`)
* **Supported platforms**: Windows 11+, Windows Server 2022+, Ubuntu 22.04 LTS+, macOS
* **Supported Python**: 3.10 – 3.13 (CPython, 64-bit; Python 3.13 recommended)

The core framework lives in the `vnpy/` package. Trading interfaces (gateways), strategy applications, database adapters, and data feeds are maintained as **separate installable packages** in the `vnpy_*` ecosystem (e.g. `vnpy_ctp`, `vnpy_ctastrategy`, `vnpy_sqlite`). They are not part of this repository but are loaded at runtime as plugins.

### Major subsystems

| Package / Module | Purpose |
| ---------------- | ------- |
| `vnpy.event` | Event-driven engine (`EventEngine`, `Event`, `HandlerType`) — the heart of the framework. |
| `vnpy.trader` | Core trading platform: `MainEngine`, `BaseEngine`, `BaseGateway`, `BaseApp`, shared data objects (`TickData`, `BarData`, `OrderData`, ...), constants, database/datafeed abstractions, UI main window, settings, logging, utilities. |
| `vnpy.alpha` | AI/ML quant research module added in v4.0: factor datasets (`dataset`), prediction models (`model`), strategy templates (`strategy`), `BacktestingEngine`, and `AlphaLab` for end-to-end research workflows. |
| `vnpy.chart` | High-performance candlestick / K-line chart widgets built on `PySide6` and `pyqtgraph`. |
| `vnpy.rpc` | Cross-process RPC client/server over ZeroMQ for distributed deployments. |
| `examples/` | Runnable demos: GUI trader, CTA backtesting, alpha research notebooks, data recorder, RPC, no-UI trading, candle chart, etc. |
| `tests/` | pytest-based tests (currently focused on `vnpy.alpha`). |

### Local workspace additions

The current working tree also contains local research/audit artifacts that are **not** part of the upstream `vnpy` core:

* `examples/czsc_strategy/` — Chan-theory (`缠论`) strategy workspace with `chan_strategy/`, `diagnostics/`, `skill_build/`, and `tests/`.
* `docs/chanlunnew/` — Local documentation and audit pack for the Chan-theory strategy (has its own `AGENTS.md`).
* Extra top-level files: `analyze_db.py`, `cosmic-ray.signals.toml`, `cosmic-ray.sqlite`, `extract_strategy.py`, `state_machine_strategy.py`, `run_state_machine_backtest.py`, `run_backtest.bat`, `.coveragerc`, `pytest.ini`.

These additions influence the current test/coverage configuration (see [Testing Strategy](#testing-strategy)) but are separate from the core framework.

---

## Key Configuration Files

| File | Purpose |
| ---- | ------- |
| `pyproject.toml` | Project metadata, dependencies, optional extras (`alpha`, `dev`), Hatchling build config, Ruff lint rules, mypy strict-mode config, mutmut config. |
| `pytest.ini` | pytest markers (`realdb`, `slow`) and deprecation warning filters. |
| `.coveragerc` | Coverage scope for the local Chan example (`examples/czsc_strategy/chan_strategy`). |
| `cosmic-ray.signals.toml` | Mutation-testing config targeting `examples/czsc_strategy/chan_strategy/signals.py`. |
| `.github/workflows/pythonapp.yml` | CI workflow: lint, type check, build on Windows. |
| `.github/dependabot.yml` | Weekly pip and GitHub Actions dependency updates targeting `dev`. |
| `docs/conf.py` | Sphinx documentation config (alabaster theme, recommonmark, autodoc). |
| `vnpy/trader/locale/build_hook.py` | Custom Hatchling build hook that compiles `vnpy/trader/locale/en/LC_MESSAGES/vnpy.po` into `.mo`. |
| `install.bat` / `install.sh` / `install_osx.sh` | Platform install scripts that bootstrap `ta-lib==0.6.4` and install the package. |

---

## Technology Stack

* **Language**: Python 3.10+
* **Build backend**: [Hatchling](https://hatchling.pypa.io/) (`hatchling.build`)
* **GUI**: PySide6 6.8.2.1, pyqtgraph, qdarkstyle
* **Numerics / Data**: NumPy 2.2+, pandas 2.2+, ta-lib 0.6.4, polars 1.26+ (alpha), pyarrow 19+ (alpha)
* **ML / Research**: scikit-learn, LightGBM, PyTorch, scipy, alphalens-reloaded, DEAP
* **Messaging / I/O**: pyzmq, requests, nbformat
* **Logging**: loguru
* **Utilities**: tqdm, qrcode, tzlocal
* **Internationalization**: Babel (`.po` → `.mo` build hook)
* **Linting / Type checking**: ruff, mypy

---

## Project Structure

```text
vnpy/                         # Core Python package
    __init__.py               # Version string (single source of truth)
    py.typed                  # PEP 561 typed-package marker
    alpha/                    # AI/ML quant research module
        dataset/              # Feature engineering & expression engine
            template.py       # AlphaDataset
            utility.py        # DataProxy, calculate_by_expression, Segment
            processor.py      # Data processors
            ts_function.py    # Time-series operators
            cs_function.py    # Cross-sectional operators
            math_function.py  # Math expression functions
            ta_function.py    # TA-Lib expression functions
            datasets/         # Pre-defined factor libraries (alpha_101, alpha_158)
        model/                # ML model templates
            template.py       # AlphaModel
            models/           # LassoModel, LgbModel, MlpModel
        strategy/             # Strategy templates & backtesting
            template.py       # AlphaStrategy
            backtesting.py    # BacktestingEngine
            strategies/       # Demo strategies
        lab.py                # AlphaLab workspace manager
        logger.py             # loguru-based logger for alpha module
    chart/                    # K-line / candlestick chart components
    event/                    # Event-driven engine
    rpc/                      # RPC client/server for distributed systems
    trader/                   # Core trading framework
        app.py                # BaseApp abstract class
        constant.py           # Enums (Direction, Exchange, Interval, ...)
        converter.py          # Offset / position conversion utilities
        database.py           # BaseDatabase abstraction + dynamic loader
        datafeed.py           # BaseDatafeed abstraction + dynamic loader
        engine.py             # BaseEngine, MainEngine, OmsEngine, LogEngine, EmailEngine, WechatEngine
        event.py              # Trading event type constants
        gateway.py            # BaseGateway abstraction
        logger.py             # loguru logger shared across trader package
        object.py             # Core dataclasses (TickData, BarData, OrderData, ...)
        optimize.py           # Parameter optimization utilities
        setting.py            # Global SETTINGS dict + vt_setting.json loader
        utility.py            # Utility functions, TZ handling, JSON helpers
        wechat.py             # WeChat notification support (iLink protocol)
        locale/               # i18n files + custom Hatchling build hook
        ui/                   # PySide6 main window and widgets
examples/                     # Example scripts and Jupyter notebooks
tests/                        # pytest-based tests (core framework)
docs/                         # Sphinx documentation (Chinese)
pyproject.toml                # Project metadata, dependencies, tool configs
install.bat / install.sh / install_osx.sh  # Platform install scripts
run_backtest.bat              # Local backtest runner script
```

---

## Build, Install, and Run

### Local editable install

```bash
# Windows (uses vnpy PyPI mirror for ta-lib prebuild wheel)
install.bat python https://pypi.vnpy.com

# Ubuntu
bash install.sh

# macOS
bash install_osx.sh

# Generic editable install (after ta-lib is present)
pip install -e ".[alpha,dev]"
```

`ta-lib==0.6.4` is a required native dependency. On Windows the install script uses a prebuilt wheel from `https://pypi.vnpy.com`; on Linux the script downloads and compiles the TA-Lib C library; on macOS it installs via Homebrew if needed.

### Build a wheel / sdist

```bash
uv build
# or
python -m build
```

The wheel build runs the custom Hatchling hook at `vnpy/trader/locale/build_hook.py`, which compiles `vnpy/trader/locale/en/LC_MESSAGES/vnpy.po` into `vnpy.mo` and force-includes it into the wheel.

### Run the GUI trader

The primary example entry point is `examples/veighna_trader/run.py`:

```python
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp

# Import desired gateway / app packages (must be installed separately)
# from vnpy_ctp import CtpGateway
# from vnpy_ctastrategy import CtaStrategyApp


def main():
    qapp = create_qapp()
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)

    # main_engine.add_gateway(CtpGateway)
    # main_engine.add_app(CtaStrategyApp)

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()
    qapp.exec()


if __name__ == "__main__":
    main()
```

### Run examples

Example launchers are in `examples/`:

* `examples/veighna_trader/` — GUI startup examples.
* `examples/candle_chart/` — Standalone K-line chart demo.
* `examples/cta_backtesting/` — CTA strategy backtesting notebooks.
* `examples/alpha_research/` — Jupyter notebooks for ML workflows.
* `examples/no_ui/` — Headless / server-style usage.
* `examples/client_server/` / `examples/simple_rpc/` — RPC demos.
* `examples/data_recorder/` — Data recorder script.
* `examples/czsc_strategy/` — Local Chan-theory strategy research workspace.

---

## Runtime Architecture

### Event-driven design

`EventEngine` (`vnpy/event/engine.py`) maintains a single dispatch thread plus a timer thread. Components publish `Event` objects with a string `type` and arbitrary `data`; handlers subscribe by event type (`register`) or as general handlers (`register_general`). Trading callbacks are implemented as event handlers. The timer thread emits `EVENT_TIMER` every second by default.

Trading event type constants are defined in `vnpy/trader/event.py`:

* `EVENT_TICK = "eTick."`
* `EVENT_TRADE = "eTrade."`
* `EVENT_ORDER = "eOrder."`
* `EVENT_POSITION = "ePosition."`
* `EVENT_ACCOUNT = "eAccount."`
* `EVENT_QUOTE = "eQuote."`
* `EVENT_CONTRACT = "eContract."`
* `EVENT_LOG = "eLog"`

Gateways push both a generic event (e.g. `EVENT_TICK`) and a symbol-specific event (e.g. `EVENT_TICK + vt_symbol`), allowing monitors to subscribe broadly or narrowly.

### Core engine hierarchy

```text
MainEngine
├── EventEngine
├── gateways: dict[str, BaseGateway]
├── engines:  dict[str, BaseEngine]
│   ├── OmsEngine       # order / trade / position / account / contract / quote management
│   ├── LogEngine       # log event handling
│   ├── EmailEngine     # SMTP notification dispatch
│   └── WechatEngine    # WeChat iLink notification dispatch
└── apps:     dict[str, BaseApp]
```

* `BaseGateway` — abstract interface for broker/market-data connections. Implementations live in external `vnpy_*` packages.
* `BaseApp` — abstract class that registers an engine class, a UI widget, and metadata with `MainEngine`.
* `BaseEngine` — abstract functional engine that receives `MainEngine` + `EventEngine`.

`MainEngine` starts the event engine, switches the working directory to `TRADER_DIR` (`~/.vntrader` by default), initializes the built-in engines, and exposes convenience methods such as `connect`, `subscribe`, `send_order`, `cancel_order`, and `query_history` that delegate to registered gateways.

### Data objects

All shared trading data classes live in `vnpy/trader/object.py` and inherit from `BaseData` (a dataclass with a `gateway_name` field):

* `TickData`, `BarData`
* `OrderData` (with `vt_orderid = f"{gateway_name}.{orderid}"`)
* `TradeData` (with `vt_tradeid = f"{gateway_name}.{tradeid}"`)
* `PositionData` (with `vt_positionid = f"{gateway_name}.{vt_symbol}.{direction.value}"`)
* `AccountData`, `ContractData`, `QuoteData`, `LogData`

Request objects include `SubscribeRequest`, `OrderRequest`, `CancelRequest`, `HistoryRequest`, and `QuoteRequest`.

### AI/ML module (`vnpy.alpha`)

```text
AlphaLab
├── AlphaDataset   # expression-based factor engineering + processors
├── AlphaModel     # Lasso / LightGBM / MLP implementations
├── AlphaStrategy  # target-position strategy template
└── BacktestingEngine  # limit-order bar-matching backtester
```

* `AlphaDataset` — builds factor datasets from an expression language (time-series, cross-sectional, math, TA-Lib functions) plus data processors (fill NA, replace inf, normalization, rank, etc.).
* `AlphaModel` — unified ML model interface with implementations for Lasso, LightGBM, and MLP.
* `AlphaStrategy` — strategy template that consumes model signals and tracks target vs. actual positions.
* `BacktestingEngine` — replay-based bar-matching backtester with Plotly performance charts.
* `AlphaLab` — orchestrates data, models, signals, and backtests in a directory-based workspace (`daily/`, `minute/`, `component/`, `dataset/`, `model/`, `signal/`).

### Plugins

Gateways, apps, databases, and datafeeds are **not** in this repo. They are installed separately and registered at runtime through:

* `main_engine.add_gateway(GatewayClass)`
* `main_engine.add_app(AppClass)`
* `SETTINGS["database.name"]` + dynamic import in `vnpy.trader.database` (fallback to `vnpy_sqlite`)
* `SETTINGS["datafeed.name"]` + dynamic import in `vnpy.trader.datafeed`

When adding support for a new broker/database/datafeed, create a new `vnpy_*` package rather than modifying this core repository.

---

## Configuration

Global settings are loaded from `vt_setting.json` in the trader runtime directory and merged into `vnpy.trader.setting.SETTINGS`. Relevant keys include:

* `database.name`, `database.database`, `database.host`, `database.port`, `database.user`, `database.password`, `database.timezone`
* `datafeed.name`, `datafeed.username`, `datafeed.password`
* `email.*` — SMTP credentials for notifications
* `log.level`, `log.console`, `log.file`
* `font.family`, `font.size`

Runtime working directory is switched to `TRADER_DIR` (the `.vntrader` folder under the user home by default, or the current working directory if it already contains `.vntrader`) when `MainEngine` starts.

---

## Testing Strategy

Tests are written with **pytest**.

### Core framework tests (`tests/`)

| Test | What it covers |
| ---- | -------------- |
| `tests/test_alpha101.py` | Validates Alpha 101 factor expressions via `calculate_by_expression` on a synthetic Polars DataFrame. |
| `tests/alpha/test_dataproxy.py` | Tests `DataProxy` arithmetic, comparison, and unary operators. |

### Local Chan example tests (`examples/czsc_strategy/tests/`)

A larger local test suite for the Chan-theory CZSC strategy, organized into:

* `unit/` — core unit tests
* `integration/` — integration tests
* `performance/` — performance smoke tests

Representative areas include signal classification, buy/sell paths, position accounting, data adapter, daily filter / no-lookahead checks, regression tests, state machine replay, and 中枢 (zhongshu) construction.

### Running tests

```bash
# Run all tests
pytest

# Run a specific core test file
pytest tests/test_alpha101.py

# Run Chan example unit tests (used by mutation testing)
pytest examples/czsc_strategy/tests/unit -q

# Skip tests that require a local historical database
pytest -m "not realdb"

# Skip slow tests
pytest -m "not slow"
```

`pytest.ini` defines two markers:

* `realdb` — requires a local historical SQLite database.
* `slow` — long-running tests.

### Mutation testing

Mutation testing is configured for the local Chan example:

* `pyproject.toml` `[tool.mutmut]` — targets `examples/czsc_strategy/chan_strategy` with tests in `examples/czsc_strategy/tests/unit`.
* `cosmic-ray.signals.toml` — targets `examples/czsc_strategy/chan_strategy/signals.py`.

### Coverage

`.coveragerc` is scoped to `examples/czsc_strategy/chan_strategy` with branch coverage enabled. Core `vnpy` coverage is not currently configured.

### CI

`.github/workflows/pythonapp.yml` runs on `push`/`pull_request` to `master` and `dev`:

1. Install Python 3.13 on `windows-latest`.
2. Install `ruff`, `mypy`, `uv`, `types-tqdm`.
3. Install `ta-lib==0.6.4` from `https://pypi.vnpy.com`.
4. Editable install with `[alpha,dev]` extras.
5. `ruff check .`
6. `mypy vnpy`
7. `uv build`
8. `python tools/sync_check.py`
9. `python tools/sync_check.py --root examples/czsc_strategy`
10. `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"`

The workflow now runs the czsc_strategy unit-test suite and both sync_check gates in CI.

---

## Code Style and Static Analysis

The project uses **ruff** for linting/formatting and **mypy** for strict static typing.

### ruff

Configuration in `pyproject.toml`:

* Target Python: 3.10
* Enabled rules: `B` (flake8-bugbear), `E` (pycodestyle error), `F` (pyflakes), `UP` (pyupgrade), `W` (pycodestyle warning)
* Line length rule `E501` is intentionally ignored

Run:

```bash
ruff check .
```

Auto-fix:

```bash
ruff check --fix .
```

### mypy

Strict mode is enabled (`disallow_untyped_defs`, `disallow_incomplete_defs`, `no_implicit_optional`, `warn_return_any`, etc.). Missing imports for `polars`, `lightgbm`, `hatchling.*`, and `qrcode` are ignored.

Run:

```bash
mypy vnpy
```

### General style conventions

* **Type annotations are required** for function signatures and important variables.
* Use `from __future__ import annotations` only where needed; the project targets Python 3.10+ and uses `X | Y` union syntax.
* Imports are grouped as: stdlib, third-party, then intra-project (relative within a package, absolute across packages).
* Docstrings are written in **English**.
* User-visible strings are translatable via `vnpy.trader.locale._` (Babel gettext).
* Data objects are `dataclass`es inheriting from `BaseData` with a `gateway_name` field.
* Event type constants are uppercase strings (`EVENT_TICK`, `EVENT_ORDER`, ...).
* Naming: `snake_case` for attributes, methods, parameters, and variables; `PascalCase` for classes; `UPPER_CASE` for constants.
* The project does **not** use `black` or `isort` in CI; rely on `ruff`.
* No pre-commit hooks are configured.

---

## Security Considerations

* **Credentials**: `vt_setting.json` stores plaintext passwords/email credentials. Do not commit this file.
* **Trading risk**: This is a live trading framework. Any change to order/position logic, gateway callbacks, or risk checks can have real financial consequences. Add defensive checks and test against paper/simulated accounts first.
* **Native dependencies**: `ta-lib` is compiled C/C++ code; ensure it comes from a trusted source (`https://pypi.vnpy.com` or official TA-Lib sources).
* **WeChat notifications**: `vnpy.trader.wechat` implements an iLink-based QR-code login flow. Session tokens are ephemeral but handle them as sensitive credentials.
* **Network gateways**: External gateway packages connect to broker APIs over the internet. Keep TLS/cert verification enabled where supported and do not disable certificate checks in production.
* **No secrets in source**: Do not hard-code API keys, passwords, or tokens in the repository.

---

## How to Contribute

1. Open an Issue for large changes; small fixes can go straight to PR.
2. Fork the repo and create a feature branch from `dev`.
3. Make focused, minimal changes.
4. Run `ruff check .` and `mypy vnpy` locally before pushing.
5. Target the `dev` branch in your Pull Request.
6. Fill out the PR template (`.github/PULL_REQUEST_TEMPLATE.md` in Chinese).

---

## Useful Commands Reference

```bash
# Linting
ruff check .

# Type checking
mypy vnpy

# Tests
pytest

# Chan example unit tests
pytest examples/czsc_strategy/tests/unit -q

# Editable install with all optional deps
pip install -e ".[alpha,dev]"

# Build wheel/sdist
uv build

# Run GUI from a custom script
python run.py
```

---

## Notes for Agents

* **No assumptions about gateway internals**: `BaseGateway` implementations are in external repos. If you need broker-specific behavior, reference the relevant `vnpy_*` package instead of guessing.
* **Event order matters**: Trading logic often depends on the order in which `EVENT_TICK`, `EVENT_ORDER`, `EVENT_TRADE`, `EVENT_POSITION`, and `EVENT_ACCOUNT` are emitted. Preserve existing event ordering.
* **Keep changes minimal**: VeighNa values stability. Prefer small, focused PRs over large refactors.
* **Docstrings in English, user text translatable**: New public APIs need English docstrings; UI strings should use `_("...")` for i18n.
* **Type hints are mandatory**: mypy strict mode is enforced in CI; untyped code will fail the build.
* **Separate local additions from core changes**: Files such as `examples/czsc_strategy/`, `docs/chanlunnew/`, and the associated coverage/mutation configs are local workspace artifacts. Be careful not to break them, but also do not treat them as upstream `vnpy` core when reasoning about framework behavior.

## sync-guardian workflow

This repository uses a root-level `HANDOFF.md` and `.synccheck.yml` to track multi-agent work.

* Inspect progress with `python tools/handoff.py status`
* Advance the stage with `python tools/handoff.py next --summary "..."` after finishing your assigned work
* Run `python tools/sync_check.py` before handing work off so version, docs, and handoff state stay aligned
* Treat `HANDOFF.md` as the single source of truth for cross-agent state
* Use `tools/handoff.py` for routine stage transitions instead of editing `HANDOFF.md` by hand
* `diagnostics_banner_check` in `.synccheck.yml` (A54) enforces that every
  `diagnostics/*.md` report carries the `RESEARCH-ONLY / NOT PROMOTION EVIDENCE`
  banner. Use `examples/czsc_strategy/diagnostics/declassify_historical_reports.py`
  to backfill missing banners.
