import sys
from pathlib import Path

import pandas as pd
import pytest


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from export_simnow_replay_snapshot import _consecutive_loss_breakdown  # noqa: E402


def test_consecutive_loss_breakdown_includes_streak_rows():
    daily = pd.DataFrame(
        {
            "equity": [1.0, 0.999, 0.998, 0.9995, 0.999, 0.9987, 0.9982],
            "daily_return": [0.0, -0.001, -0.001001, 0.001503, -0.0005, -0.0003003, -0.0005007],
        },
        index=pd.to_datetime(
            [
                "2026-07-18",
                "2026-07-19",
                "2026-07-20",
                "2026-07-21",
                "2026-07-22",
                "2026-07-23",
                "2026-07-24",
            ]
        ).date,
    )

    result = _consecutive_loss_breakdown(daily)

    assert result["days"] == 3
    assert result["start_date"] == "2026-07-22"
    assert result["end_date"] == "2026-07-24"
    assert result["cumulative_return_pct"] == pytest.approx(-0.1301)
    assert result["rows"] == [
        {"date": "2026-07-22", "daily_return_pct": pytest.approx(-0.05), "equity": 0.999},
        {"date": "2026-07-23", "daily_return_pct": pytest.approx(-0.03003), "equity": 0.9987},
        {"date": "2026-07-24", "daily_return_pct": pytest.approx(-0.05007), "equity": 0.9982},
    ]


def test_consecutive_loss_breakdown_is_empty_without_losses():
    daily = pd.DataFrame(
        {
            "equity": [1.0, 1.001],
            "daily_return": [0.0, 0.001],
        },
        index=pd.to_datetime(["2026-07-23", "2026-07-24"]).date,
    )

    result = _consecutive_loss_breakdown(daily)

    assert result["days"] == 0
    assert result["start_date"] is None
    assert result["rows"] == []
