from __future__ import annotations

import copy
from typing import Any

from sc_short_weight_neighborhood import params_for_multiplier


CANDIDATE_NAME = "sc025_a_zn010_sc3buy_half + A/AP trailing 250/0.20"
DEFAULT_SC_SHORT_MULTIPLIER = 0.25
FINAL_SC_MULTIPLIERS = [0.10, 0.20, 0.25, 0.30, 0.40, 0.50]


def final_candidate_params(multiplier: float = DEFAULT_SC_SHORT_MULTIPLIER, symbol: str = "AP888") -> dict[str, Any]:
    """Return the final platform candidate params for one requested symbol.

    The base is params_for_multiplier, so existing second-buy filters and
    trailing defaults stay aligned with the broader diagnostics.
    """
    params = params_for_multiplier(multiplier, symbol)
    params["block_1buy_daily_down"] = True
    params["enable_short"] = True
    params["enable_short_symbols"] = ["SC888", "A888", "ZN888"]
    params["symbol_position_overrides"] = {
        "A888": {"pos_1sell": 0.01, "pos_2sell": 0.02, "pos_3sell": 0.03},
        "ZN888": {"pos_1sell": 0.01, "pos_2sell": 0.02, "pos_3sell": 0.03},
        "SC888": {"pos_3buy": 0.15},
    }
    trailing = copy.deepcopy(params.get("trailing_overrides") or {})
    trailing.update({
        "A888": {"trailing_start_bp": 250, "trailing_drawback_pct": 0.20},
        "AP888": {"trailing_start_bp": 250, "trailing_drawback_pct": 0.20},
    })
    params["trailing_overrides"] = trailing
    return params


def candidate_summary() -> dict[str, Any]:
    return {
        "candidate": CANDIDATE_NAME,
        "base": {
            "block_1buy_daily_down": True,
            "sc_short_multiplier": DEFAULT_SC_SHORT_MULTIPLIER,
        },
        "strategy_config_overrides": final_candidate_params(DEFAULT_SC_SHORT_MULTIPLIER, "AP888"),
    }
