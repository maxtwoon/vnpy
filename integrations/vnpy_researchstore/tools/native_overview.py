"""Entry command: print the snapshot-only native bar overview + diagnostics.

Usage:
    python tools/native_overview.py --config configs/native_backtest.json

Runs the same guarded bootstrap as backtests (fresh process required), then
prints {"overview": [...], "diagnostics": [...]} as JSON on stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vnpy_researchstore.bootstrap import (  # noqa: E402  (sys.path first)
    bootstrap_session,
    load_config,
)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="native snapshot bar overview")
    parser.add_argument("--config", required=True, help="bootstrap config JSON")
    args = parser.parse_args(argv)

    config, identity = load_config(args.config)
    session = bootstrap_session(config, identity)
    overview = [
        {
            "symbol": o.symbol,
            "exchange": o.exchange.value if o.exchange else None,
            "interval": o.interval.value if o.interval else None,
            "count": o.count,
            "start": o.start.isoformat() if o.start else None,
            "end": o.end.isoformat() if o.end else None,
        }
        for o in session.database.get_bar_overview()
    ]
    print(
        json.dumps(
            {
                "config_identity": identity,
                "snapshot_id": session.database.snapshot_id,
                "overview": overview,
                "diagnostics": session.database.diagnostics,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
