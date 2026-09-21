"""Read the current ledger, never execute its illustrative call strings."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re


def read_registry(root: Path) -> tuple[dict, str]:
    """Load an internally consistent file snapshot for one request."""
    raw = (root / "registry" / "data_sources.json").read_bytes()
    db = json.loads(raw)
    if not isinstance(db.get("sources"), dict) or not isinstance(db.get("routing"), dict):
        raise ValueError("invalid_registry_schema")
    return db, hashlib.sha256(raw).hexdigest()


def supported() -> dict[str, list[str]]:
    """Return implemented handlers, separate from registry availability."""
    from .providers_sdk import SUPPORTED as sdk
    from .providers_http import SUPPORTED as http
    return {sid: sorted(set(sdk.get(sid, []) + http.get(sid, []))) for sid in sdk.keys() | http.keys()}


def unavailable(db: dict, source_id: str, recipe: str) -> str | None:
    """Apply live source, capability, freshness and endpoint exclusions."""
    source = db["sources"].get(source_id)
    if not source:
        return "unknown_source"
    if source.get("status") not in {"verified", "degraded"}:
        return source.get("status", "unverified")
    monitoring = source.get("monitoring") or {}
    if source.get("enabled") is False or monitoring.get("enabled") is False:
        return "disabled"
    if monitoring.get("requires_recheck"):
        return "requires_recheck"
    try:
        last = datetime.fromisoformat(monitoring.get("last_conclusive_at") or source.get("verified_on", ""))
        last = last.replace(tzinfo=timezone.utc) if last.tzinfo is None else last
        now = datetime.now(timezone.utc)
        if last > now + timedelta(minutes=5) or now - last > timedelta(days=14):
            return "stale_verification"
    except (ValueError, TypeError):
        return "stale_verification"
    spec = source.get("invoke", {}).get(recipe)
    if not isinstance(spec, dict):
        return "no_recipe"
    if spec.get("enabled") is False or spec.get("status") == "blocked":
        return "recipe_disabled"
    obs = monitoring.get("observations", {}).get(recipe, {})
    if obs.get("status") in {"FAIL", "UNKNOWN"}:
        return "latest_capability_" + obs["status"].lower()
    if source["status"] == "degraded" and obs.get("status") != "PASS":
        return "degraded_capability_unverified"
    for failure in monitoring.get("unresolved_failures", []):
        if isinstance(failure, dict) and failure.get("capability") == recipe:
            return "unresolved_capability_failure"
    call = str(spec.get("call", ""))
    for owner in (source, db["sources"].get("akshare", {}), db["sources"].get("efinance", {})):
        for name in owner.get("blocked_functions", {}):
            if re.search(r"\b" + re.escape(name) + r"\b", call):
                return "blocked_function"
    for owner in (source, db["sources"].get("eastmoney", {})):
        for endpoint, state in owner.get("endpoint_status", {}).items():
            if isinstance(state, dict) and state.get("status") == "blocked" and endpoint in call:
                return "blocked_endpoint"
    if source_id == "tushare" and "minute" in recipe:
        return "minute_not_authorized"
    if recipe not in supported().get(source_id, []):
        return "adapter_not_implemented"
    return None

