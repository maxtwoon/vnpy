import sys
from pathlib import Path
from unittest.mock import patch

import pytest


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from diagnostics.backtest_matrix_report import evaluate_oos_gate  # noqa: E402
from diagnostics.cost_sensitivity_report import (  # noqa: E402
    _compute_deltas,
    run_cost_sensitivity,
    write_markdown,
)
from diagnostics.risk_param_sensitivity_report import evaluate_perturbation_gate  # noqa: E402


def _report(total_return_pct: float, max_drawdown_pct: float = 5.0, sharpe_ratio: float = 0.5) -> dict:
    return {
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "sharpe_ratio": sharpe_ratio,
        "total_trades": 10,
    }


class TestOOSGate:
    def test_sign_flip_is_flagged(self) -> None:
        matrix = {
            "symbols": {
                "SYM": {
                    "in_sample": _report(10.0, 5.0),
                    "out_sample": _report(-3.0, 8.0),
                }
            }
        }
        gate = evaluate_oos_gate(matrix)
        assert gate["SYM"]["ok"] is False
        assert "sign flip" in " ".join(gate["SYM"]["issues"])
        assert gate["SYM"]["return_ratio"] == pytest.approx(-0.3)
        assert gate["SYM"]["drawdown_ratio"] == pytest.approx(1.6)

    def test_same_sign_is_ok(self) -> None:
        matrix = {
            "symbols": {
                "SYM": {
                    "in_sample": _report(10.0, 5.0),
                    "out_sample": _report(4.0, 6.0),
                }
            }
        }
        gate = evaluate_oos_gate(matrix)
        assert gate["SYM"]["ok"] is True
        assert gate["SYM"]["issues"] == []
        assert gate["SYM"]["return_ratio"] == pytest.approx(0.4)

    def test_zero_is_return_handles_ratio(self) -> None:
        matrix = {
            "symbols": {
                "SYM": {
                    "in_sample": _report(0.0, 0.0),
                    "out_sample": _report(4.0, 6.0),
                }
            }
        }
        gate = evaluate_oos_gate(matrix)
        assert gate["SYM"]["ok"] is True
        assert gate["SYM"]["return_ratio"] is None
        assert gate["SYM"]["drawdown_ratio"] is None

    def test_error_report_is_not_ok(self) -> None:
        matrix = {
            "symbols": {
                "SYM": {
                    "in_sample": {"error": "db missing"},
                    "out_sample": _report(4.0),
                }
            }
        }
        gate = evaluate_oos_gate(matrix)
        assert gate["SYM"]["ok"] is False


class TestPerturbationGate:
    def test_variant_sign_flip_is_flagged(self) -> None:
        payload = {
            "symbols": {
                "SYM": {
                    "baseline": _report(10.0),
                    "tight": _report(-5.0),
                    "loose": _report(7.0),
                }
            }
        }
        gate = evaluate_perturbation_gate(payload)
        assert gate["SYM"]["ok"] is False
        assert any("tight" in issue for issue in gate["SYM"]["issues"])
        assert gate["SYM"]["max_abs_delta_pct"] == pytest.approx(15.0)

    def test_no_sign_flip_is_ok(self) -> None:
        payload = {
            "symbols": {
                "SYM": {
                    "baseline": _report(10.0),
                    "tight": _report(6.0),
                    "loose": _report(12.0),
                }
            }
        }
        gate = evaluate_perturbation_gate(payload)
        assert gate["SYM"]["ok"] is True
        assert gate["SYM"]["max_abs_delta_pct"] == pytest.approx(4.0)

    def test_baseline_error_is_not_ok(self) -> None:
        payload = {
            "symbols": {
                "SYM": {
                    "baseline": {"error": "failed"},
                    "tight": _report(6.0),
                }
            }
        }
        gate = evaluate_perturbation_gate(payload)
        assert gate["SYM"]["ok"] is False


class TestCostSensitivity:
    def test_compute_deltas(self) -> None:
        baseline = _report(10.0, 5.0, 0.5)
        reports = {
            "x1.0": baseline,
            "x1.5": _report(7.0, 5.5, 0.3),
            "x2.0": _report(4.0, 6.0, 0.1),
        }
        deltas = _compute_deltas(baseline, reports, (1.0, 1.5, 2.0))
        assert deltas["x1.0"]["delta_return_pct"] == pytest.approx(0.0)
        assert deltas["x1.5"]["delta_return_pct"] == pytest.approx(-3.0)
        assert deltas["x2.0"]["delta_return_pct"] == pytest.approx(-6.0)
        assert deltas["x2.0"]["relative_return_pct"] == pytest.approx(-60.0)

    def test_compute_deltas_with_error(self) -> None:
        deltas = _compute_deltas(None, {}, (1.0,))
        assert "error" in deltas

    def test_run_cost_sensitivity_mocks_run_one(self) -> None:
        calls: list[tuple[str, float, float]] = []

        def fake_run_one(
            db_path: Path,
            symbol: str,
            start: str,
            end: str,
            quiet: bool = True,
            commission_rate: float = 0.0,
            slippage: float = 0.0,
            **kwargs: object,
        ) -> dict:
            calls.append((symbol, commission_rate, slippage))
            mult = commission_rate / 0.0001
            return _report(10.0 - 2.0 * (mult - 1.0), 5.0 + 0.5 * (mult - 1.0), 0.5 - 0.1 * (mult - 1.0))

        with patch("diagnostics.cost_sensitivity_report.run_one", fake_run_one):
            payload = run_cost_sensitivity(
                Path("/tmp/fake.db"), ["RB888"], "2024-01-01", "2024-12-31"
            )

        assert len(calls) == 3
        assert calls[0] == ("RB888", pytest.approx(0.0001), pytest.approx(0.0005))
        assert calls[1] == ("RB888", pytest.approx(0.00015), pytest.approx(0.00075))
        assert calls[2] == ("RB888", pytest.approx(0.0002), pytest.approx(0.001))

        deltas = payload["symbols"]["RB888"]["deltas"]
        assert deltas["x1.5"]["delta_return_pct"] == pytest.approx(-1.0)
        assert deltas["x2.0"]["delta_return_pct"] == pytest.approx(-2.0)

    def test_write_markdown_includes_banner_and_table(self, tmp_path: Path) -> None:
        payload = {
            "generated_at": "2024-01-01T00:00:00+00:00",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "base_commission_rate": 0.0001,
            "base_slippage": 0.0005,
            "multipliers": [1.0, 2.0],
            "symbols": {
                "RB888": {
                    "x1.0": _report(10.0, 5.0, 0.5),
                    "x2.0": _report(6.0, 6.0, 0.3),
                    "deltas": {
                        "x1.0": {"delta_return_pct": 0.0, "delta_max_drawdown_pct": 0.0, "delta_sharpe": 0.0},
                        "x2.0": {"delta_return_pct": -4.0, "delta_max_drawdown_pct": 1.0, "delta_sharpe": -0.2},
                    },
                }
            },
        }
        out = tmp_path / "cost.md"
        write_markdown(payload, out)
        text = out.read_text(encoding="utf-8")
        assert "RESEARCH-ONLY / NOT PROMOTION EVIDENCE" in text
        assert "成本/滑点敏感性报告" in text
        assert "RB888" in text
        assert "2.0x" in text
        assert "-4.00%" in text
