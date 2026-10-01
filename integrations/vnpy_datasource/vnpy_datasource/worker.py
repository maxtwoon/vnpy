"""Single-request read-only provider worker, launched by registry/ds.py run."""

import contextlib
import json
import os
from pathlib import Path
import re
import socket
import sys

# A file entry point runs in dataSource's environment, without installing vnpy there.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vnpy_datasource.registry import read_registry, unavailable  # noqa: E402
from vnpy_datasource.validation import validate_bars  # noqa: E402


def execute(payload: dict) -> dict:
    """Select a fixed handler after checking the live ledger again."""
    root = Path(payload["root"]).resolve()
    db, digest = read_registry(root)
    if digest != payload["registry_sha256"]:
        return {"status": "error", "reason": "registry_changed_retry_request"}
    sid, recipe = payload["source"], payload["recipe"]
    reason = unavailable(db, sid, recipe)
    if reason:
        return {"status": "source_unavailable", "reason": reason}
    sys.path.insert(0, str(root / "registry"))
    from maintenance_core import load_secrets
    secrets = load_secrets(root)
    proxy = secrets.get("HTTPS_PROXY") or secrets.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if sid == "yfinance" and not proxy:
        match = re.search(r"127\.0\.0\.1:\d+", db.get("host_profile", {}).get("proxy", ""))
        if match:
            proxy = "http://" + match.group()
    source = db["sources"][sid]
    required = (source.get("auth") or {}).get("env", [])
    if isinstance(required, str):
        required = [required]
    if sid == "tqsdk":
        required = ["TQ_USERNAME", "TQ_PASSWORD"]
    if any(not secrets.get(k) for k in required if not k.endswith("_URL")):
        return {"status": "source_unavailable", "reason": "credential_missing"}
    socket.setdefaulttimeout(20)
    import requests
    original_request = requests.sessions.Session.request

    def guarded_request(session, method, url, **kwargs):
        # SDK HTTP calls use the same endpoint exclusions as handwritten providers.
        for owner in (source, db["sources"].get("eastmoney", {})):
            for endpoint, state in owner.get("endpoint_status", {}).items():
                if isinstance(state, dict) and state.get("status") == "blocked" and endpoint in str(url):
                    raise ValueError("blocked_endpoint")
        if sid != "yfinance":
            session.trust_env = False
            kwargs["proxies"] = {"http": None, "https": None}
        requested_timeout = kwargs.get("timeout") or 20
        if isinstance(requested_timeout, tuple):
            kwargs["timeout"] = tuple(min(float(t or 20), 20) for t in requested_timeout)
        else:
            kwargs["timeout"] = min(float(requested_timeout), 20)
        return original_request(session, method, url, **kwargs)

    # Only this short-lived worker is changed; the Studio process is untouched.
    requests.sessions.Session.request = guarded_request
    if sid != "yfinance":
        for key in tuple(os.environ):
            if key.upper().endswith("_PROXY"):
                os.environ.pop(key, None)
    from vnpy_datasource import providers_http, providers_sdk
    module = providers_http if recipe in providers_http.SUPPORTED.get(sid, []) else providers_sdk
    context = {"root": str(root), "db": db, "secrets": secrets, "timeout": 20, "proxy_url": proxy}
    result = module.query(sid, recipe, payload["params"], context)
    if result.get("kind") == "bar_batch":
        rows = []
        per_symbol = {}
        for symbol in payload["params"]["symbols"]:
            part = validate_bars({"kind": "bars", "metadata": result["metadata"],
                                  "records": [row for row in result["records"] if row["symbol"] == symbol]},
                                 {**payload["params"], "symbol": symbol})
            rows.extend({"symbol": symbol, **row} for row in part["records"])
            per_symbol[symbol] = part["metadata"]
        result["records"] = rows
        result["metadata"]["per_symbol"] = per_symbol
    if payload.get("require_bars") or result.get("kind") == "bars":
        result = validate_bars(result, payload["params"])
    if not isinstance(result.get("records"), list):
        raise ValueError("invalid_records_schema")
    result["status"] = "ok" if result["records"] else "no_data"
    result.setdefault("metadata", {}).setdefault("point_in_time_guaranteed", False)
    # Scrub credentials recursively without rewriting numeric/date data or schemas.
    from maintenance_core import redact

    def scrub(value):
        if isinstance(value, str):
            return redact(value, secrets)
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        return value

    return scrub(result)


def main() -> None:
    """Keep stdout as exactly one JSON object; suppress SDK diagnostic text."""
    try:
        payload = json.load(sys.stdin)
        with open(os.devnull, "w", encoding="utf-8") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            result = execute(payload)
        rendered = json.dumps(result, ensure_ascii=False, allow_nan=False)
    except Exception as exc:
        # Never return arbitrary SDK error messages, tokens, URLs, or raw stderr.
        code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[a-z][a-z0-9_]{2,80}", str(exc)) else "provider_" + type(exc).__name__.lower()
        rendered = json.dumps({"status": "unsupported" if code.startswith("unsupported") else "error", "reason": code})
    sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
