import pytest


@pytest.mark.realdb
@pytest.mark.slow
def test_real_db_available_for_manual_matrix(real_db_path):
    if not real_db_path.exists():
        pytest.skip("real DB not available")
    assert real_db_path.stat().st_size > 0


@pytest.mark.realdb
@pytest.mark.slow
def test_real_db_continuous_contract_evidence(real_db_path):
    if not real_db_path.exists():
        pytest.skip("real DB not available")

    import sys
    from pathlib import Path

    diag = Path(__file__).resolve().parents[2] / "diagnostics"
    if str(diag) not in sys.path:
        sys.path.insert(0, str(diag))

    from audit_issue_diagnostics import analyze_continuous_contract_assumptions

    symbols = ["AP888", "RB888", "SC888", "A888", "ZN888"]
    result = analyze_continuous_contract_assumptions(str(real_db_path), symbols)

    assert result["issue"] == "H4"
    assert result["status"] not in ("unknown", "unavailable")
    assert result.get("silently_pass") is False
    assert result.get("db_path") is not None
    assert any(
        result["real_symbol_transitions"].get(sym, {}).get("distinct_count", 0) > 1
        for sym in symbols
    ), f"expected at least one symbol with multiple real_symbol transitions, got {result['real_symbol_transitions']}"
