"""Repository hygiene guards for legacy local artifacts."""
from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_backtest_idempotent_regression_lives_under_unit_tests():
    assert not (PROJECT_ROOT / "test_backtest_idempotent.py").exists()
    assert (PROJECT_ROOT / "tests" / "unit" / "test_backtest_idempotent.py").exists()


def test_one_shot_patch_scripts_are_explicitly_labeled_legacy():
    for name in (
        "archive/one_shot_scripts/patch_backtest_1.py",
        "archive/one_shot_scripts/patch_backtest_2.py",
        "archive/one_shot_scripts/patch_backtest_3.py",
        "archive/one_shot_scripts/patch_backtest_4.py",
    ):
        header = "\n".join((PROJECT_ROOT / name).read_text(encoding="utf-8").splitlines()[:8])
        assert "ONE-SHOT" in header
        assert "LEGACY" in header


def test_obsolete_data_cache_csv_files_are_not_git_tracked():
    repo_root = PROJECT_ROOT.parents[1]
    completed = subprocess.run(
        ["git", "ls-files", "examples/czsc_strategy/data_cache/*.csv"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == ""


def test_in_flight_changes_manifest_documents_uncommitted_simnow_work():
    manifest = PROJECT_ROOT / "IN_FLIGHT_CHANGES.md"
    text = manifest.read_text(encoding="utf-8")

    assert "SimNow" in text
    assert "diagnostics/" in text
    assert "tests/unit/" in text
    assert "commit or stash" in text
    assert "risk-halt decision" in text
    assert "20 valid" in text
    lowered = text.lower()
    for forbidden in ("password", "auth code", "api key", "account id"):
        assert forbidden not in lowered


def test_drawdown_breaker_docs_include_weight_based_coordinator_scope():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "chan_strategy" / "config.py").read_text(encoding="utf-8")

    assert "PortfolioCoordinator" in readme
    assert "weight-based" in readme
    assert "PortfolioCoordinator" in config
    assert "weight-based" in config
    assert "暂未接入" not in config


def test_risk_parity_docs_disclose_every_bar_no_turnover_and_dropout_concentration():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "chan_strategy" / "config.py").read_text(encoding="utf-8")

    for text in (readme, config):
        assert "risk_parity_rebalance_policy" in text
        assert "every_bar" in text
        assert "risk_parity_turnover_control" in text
        assert "turnover" in text
        assert "dropout" in text
        assert "concentration" in text


def test_limit_halt_docs_disclose_settlement_basis_and_close_fallback():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    limit_config = (PROJECT_ROOT / "chan_strategy" / "limit_config.py").read_text(encoding="utf-8")

    for text in (readme, limit_config):
        assert "settlement" in text
        assert "previous close" in text
        assert "fallback" in text


def test_limit_halt_docs_disclose_touch_based_enforcement_methodology():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    limit_config = (PROJECT_ROOT / "chan_strategy" / "limit_config.py").read_text(encoding="utf-8")

    for text in (readme, limit_config):
        assert "high/low" in text
        assert "touch" in text
        assert "conservative" in text


def test_limit_halt_docs_disclose_temporary_widening_manual_verification_status():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    limit_config = (PROJECT_ROOT / "chan_strategy" / "limit_config.py").read_text(encoding="utf-8")

    for text in (readme, limit_config):
        assert "temporary_widening_windows" in text
        assert "manual_confirmation_required" in text
        assert "not independently verified" in text
        assert "primary exchange notice" in text


def test_limit_halt_docs_disclose_rollover_splice_suppression():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "chan_strategy" / "config.py").read_text(encoding="utf-8")

    for text in (readme, config):
        assert "splice" in text
        assert "suppress" in text
        assert "limit_halt_rollover_suppressed_bars" in text


def test_rollover_gating_docs_disclose_ex_post_full_window_detection():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "chan_strategy" / "config.py").read_text(encoding="utf-8")

    for text in (readme, config):
        assert "rollover_open_gating" in text
        assert "full-window" in text
        assert "ex-post" in text
        assert "protective" in text


def test_unparseable_row_rate_docs_disclose_formal_fail_closed_threshold():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "chan_strategy" / "config.py").read_text(encoding="utf-8")

    for text in (readme, config):
        assert "max_unparseable_row_rate" in text
        assert "fail-closed" in text
        assert "0.001" in text


def test_price_tick_rounding_docs_disclose_formal_contract_spec_scope():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "chan_strategy" / "config.py").read_text(encoding="utf-8")

    for text in (readme, config):
        assert "price_tick_rounding" in text
        assert "contract_specs" in text
        assert "tick" in text
        assert "formal" in text


def test_margin_model_docs_disclose_exchange_minimum_and_no_broker_liquidation():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "chan_strategy" / "config.py").read_text(encoding="utf-8")

    for text in (readme, config):
        assert "margin_model_caveat" in text
        assert "exchange-minimum" in text
        assert "maintenance" in text
        assert "broker" in text
        assert "forced liquidation" in text


def test_slippage_cost_docs_disclose_single_side_round_trip_formula():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "chan_strategy" / "config.py").read_text(encoding="utf-8")

    for text in (readme, config):
        assert "slippage_application" in text
        assert "single-side" in text
        assert "round-trip" in text
        assert "2 * commission_rate + slippage" in text


def test_long_short_overlap_docs_disclose_independent_policy_and_metric():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "chan_strategy" / "config.py").read_text(encoding="utf-8")

    for text in (readme, config):
        assert "long_short_overlap_policy" in text
        assert "independent_long_short_substrategies" in text
        assert "both_long_short_bars" in text
        assert "enable_short=True" in text
        assert "regime_model=\"independent\"" in text


def test_signal_assumption_docs_cover_turnover_stability_terms_and_unconfirmed_zs():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    signals = (PROJECT_ROOT / "chan_strategy" / "signals.py").read_text(encoding="utf-8")

    for text in (readme, signals):
        assert "预期换手" in text
        assert "稳定性假设" in text
        assert "缠论术语表.md" in text
        assert "score=30" in text
        assert "score=40" in text
def test_production_signal_modules_link_terms_to_non_authoritative_glossary():
    zhongshu = (PROJECT_ROOT / "chan_strategy" / "zhongshu.py").read_text(encoding="utf-8")
    sell_signals = (PROJECT_ROOT / "chan_strategy" / "sell_signals.py").read_text(encoding="utf-8")

    for text in (zhongshu, sell_signals):
        assert "skill_build/reference" in text
        assert "缠论术语表.md" in text
        assert "non-authoritative" in text
        assert "workspace mapping" in text
