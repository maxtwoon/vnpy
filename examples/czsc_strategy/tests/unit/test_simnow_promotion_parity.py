"""Parity regression pin for the two 20-day SimNow promotion-readiness implementations.

WHY THIS TEST EXISTS (3rd comprehensive re-audit, finding M-NEW-3 — see
``diagnostics/diagnostics_ai_stock_review_report_2026-07-22c.md``):

Two independently-maintained functions compute the "20-day SimNow promotion
readiness" verdict from the same ``simnow_observation_ledger.jsonl`` data:

- ``diagnostics/simnow_daily_monitor.py::build_20d_report`` — ``halt_days`` also
  checks ``order_safety.status == "halt"``; ``consistency_matched_days`` requires
  ``consistency.matched is True AND consistency.verified is True``.
- ``diagnostics/simnow_promotion_decision.py::decide_promotion`` — ``halt_days``
  only checks ``thresholds.status == "halt"``; ``consistency_matched_days``
  accepts any truthy ``consistency.matched``.

These sub-count computations genuinely DIVERGE today. The final verdicts still
agree only because both functions gate ``ready_to_expand`` first on
``valid_observation_days >= min_days``, and the shared
``is_valid_observation()`` gate (``diagnostics/simnow_observation_rules.py``) is
strictly stricter than either diverging sub-check — so any day that would make
the two implementations disagree is already excluded from the valid-day count.

This test is deliberately a PARITY PIN, not a claim that the duplication has
been resolved: it pins the currently-incidental safety-net property so that any
future edit to either function (or to ``is_valid_observation``) that lets the
sub-count divergence propagate into a ``ready_to_expand`` disagreement fails CI
immediately. Consolidating the two implementations is explicitly out of scope
here — both files belong to a live, concurrently-running SimNow workstream.
"""

import sys
from pathlib import Path
from typing import Any


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_daily_monitor import build_20d_report  # noqa: E402
from simnow_observation_rules import is_valid_observation  # noqa: E402
from simnow_promotion_decision import decide_promotion  # noqa: E402


MIN_DAYS = 20


def _clean_day(date: str) -> dict[str, Any]:
    """A minimal ledger row that passes every is_valid_observation() gate."""
    return {
        "date": date,
        "status": "pass",
        "consistency": {"matched": True, "verified": True, "reason": ""},
        "thresholds": {"status": "pass", "rows": []},
        "order_safety": {"status": "pass"},
        "subscription_coverage": {"missing_symbols": []},
        "kline_coverage": {"missing_symbols": [], "short_symbols": []},
        "valid_observation": True,
    }


def _clean_window(n: int = MIN_DAYS) -> list[dict[str, Any]]:
    """n consecutive fully-valid observation days (2026-06-01 .. )."""
    return [_clean_day(f"2026-06-{i:02d}") for i in range(1, n + 1)]


def test_clean_window_both_implementations_agree_ready():
    records = _clean_window()
    assert all(is_valid_observation(row) for row in records)

    report = build_20d_report(records, min_days=MIN_DAYS)
    decision = decide_promotion(records, min_days=MIN_DAYS)

    assert report["valid_observation_days"] == MIN_DAYS
    assert decision["valid_observation_days"] == MIN_DAYS
    assert report["ready_to_expand"] is True
    assert decision["ready_to_expand"] is True
    assert report["ready_to_expand"] == decision["ready_to_expand"]


def test_divergent_subcounts_but_verdicts_still_agree():
    """Exercise the M-NEW-3 divergence directly.

    Day A: ``order_safety.status == "halt"`` but ``thresholds.status != "halt"``
    -> counted as a halt day ONLY by build_20d_report.
    Day B: ``consistency.matched is True`` but ``consistency.verified is False``
    -> counted as a matched day ONLY by decide_promotion.

    Both days are excluded from ``valid_observation_days`` by the shared,
    stricter ``is_valid_observation()`` gate, so the final verdicts must still
    agree (both False) even though the sub-counts provably differ. If a future
    change ever lets this divergence reach ``ready_to_expand``, this test fails.
    """
    records = _clean_window(MIN_DAYS - 2)

    day_a = _clean_day("2026-06-19")
    day_a["status"] = "halt"
    day_a["order_safety"] = {"status": "halt"}
    day_a["consistency"]["reason"] = "workflow_order_safety_breach"
    day_a["valid_observation"] = False

    day_b = _clean_day("2026-06-20")
    day_b["consistency"] = {
        "matched": True,
        "verified": False,
        "reason": "consistency_provenance_unverified",
    }
    day_b["valid_observation"] = False

    records.extend([day_a, day_b])
    assert is_valid_observation(day_a) is False
    assert is_valid_observation(day_b) is False

    report = build_20d_report(records, min_days=MIN_DAYS)
    decision = decide_promotion(records, min_days=MIN_DAYS)

    # The parity pin: final verdicts agree despite the divergent sub-counts.
    assert report["ready_to_expand"] is False
    assert decision["ready_to_expand"] is False
    assert report["ready_to_expand"] == decision["ready_to_expand"]
    assert report["valid_observation_days"] == MIN_DAYS - 2
    assert decision["valid_observation_days"] == MIN_DAYS - 2
    assert "need_2_more_valid_observation_days" in report["promotion_blockers"]
    assert "need_2_more_valid_observation_days" in decision["promotion_blockers"]

    # Regression documentation: the sub-counts genuinely diverge today.
    # build_20d_report counts order_safety halts; decide_promotion does not.
    assert report["halt_days"] == 1
    assert decision["halt_days"] == 0
    assert report["halt_days"] != decision["halt_days"]
    # decide_promotion counts truthy matched; build_20d_report also requires verified.
    assert report["consistency_matched_days"] == MIN_DAYS - 1
    assert decision["consistency_matched_days"] == MIN_DAYS
    assert report["consistency_matched_days"] != decision["consistency_matched_days"]


def test_insufficient_valid_days_both_agree_not_ready():
    records = _clean_window(5)
    for i in range(6, MIN_DAYS + 1):
        day = _clean_day(f"2026-06-{i:02d}")
        day["status"] = "pending"
        day["consistency"] = {
            "matched": False,
            "verified": False,
            "reason": "historical_db_lag",
        }
        day["valid_observation"] = False
        records.append(day)

    report = build_20d_report(records, min_days=MIN_DAYS)
    decision = decide_promotion(records, min_days=MIN_DAYS)

    # Both must reject for the SAME underlying reason: not enough valid days.
    assert report["valid_observation_days"] == 5
    assert decision["valid_observation_days"] == 5
    assert report["ready_to_expand"] is False
    assert decision["ready_to_expand"] is False
    assert report["ready_to_expand"] == decision["ready_to_expand"]
    assert "need_15_more_valid_observation_days" in report["promotion_blockers"]
    assert "need_15_more_valid_observation_days" in decision["promotion_blockers"]
    # Sub-counts agree on this window (no divergent days present).
    assert report["halt_days"] == decision["halt_days"] == 0
    assert report["consistency_matched_days"] == decision["consistency_matched_days"] == 5
