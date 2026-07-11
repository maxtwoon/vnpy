"""Shared SimNow monitor configuration.

This module holds the safety-first defaults for the SimNow diagnostics layer.
A diagnostic that cannot verify something must report
``unavailable``/``unproven``/``pending``, never silently default to ``pass``.
"""

from __future__ import annotations


SIMNOW_MONITOR_CONFIG: dict[str, str] = {
    # Finding #2 fix. When "replay_first" (default), a risk block sourced from
    # simnow_daily_capture.py's known-placeholder build_risk() output is never
    # silently treated as authoritative for threshold evaluation; it is
    # reported separately and labeled. "legacy_simnow_first" reproduces the
    # old behavior for A/B diffing only.
    "risk_priority": "replay_first",

    # Finding #3 fix. Governs whether compare_simnow_replay treats a
    # replay-derived comparison surface as a pass/fail verdict, or as
    # "unavailable".
    "consistency_source_mode": "require_captured",

    # Finding #4 fix. Governs whether simnow_tick_bars.py writes straight to
    # {symbol}_1M_raw or to a staging table requiring an explicit promote step.
    # "direct" additionally requires the --allow-direct-write CLI flag.
    "kline_write_mode": "staging",
}
