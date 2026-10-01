"""Bounded subprocess client; provider dependencies stay in dataSource."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .registry import read_registry, supported, unavailable


class DataSourceError(RuntimeError):
    """The local bridge could not produce a valid response."""


class DataSourceClient:
    """Read historical and research data without opening a trading gateway."""

    def __init__(self, root: str | Path = "D:/repo/dataSource", timeout: float = 90) -> None:
        self.root = Path(root).resolve()
        if not 1 <= timeout <= 600:
            raise ValueError("timeout_must_be_between_1_and_600")
        self.timeout = float(timeout)

    def describe(self) -> dict:
        """List ledger recipes and their current adapter availability."""
        db, digest = read_registry(self.root)
        sources = {}
        for sid, source in db["sources"].items():
            recipes = {}
            for recipe in source.get("invoke", {}):
                reason = unavailable(db, sid, recipe)
                recipes[recipe] = {"callable": reason is None, "reason": reason}
            sources[sid] = {"name": source.get("name"), "status": source.get("status"), "recipes": recipes}
        return {"root": str(self.root), "registry_sha256": digest,
                "sources": sources, "routing": {k: v for k, v in db["routing"].items() if not k.startswith("_")},
                "implemented": supported(), "runtime_ready": self._runtime_ready(db)}

    def _runtime_ready(self, db: dict) -> bool:
        active = db.get("maintenance", {}).get("runtime", {}).get("active_env")
        if not active:
            return False
        env = (self.root / active).resolve()
        allowed = (self.root / ".maintenance" / "envs").resolve()
        return env.is_relative_to(allowed) and env != allowed and (env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")).is_file()

    def query_source(self, source: str, recipe: str, params: dict | None = None) -> dict:
        """Call one explicit source recipe, preserving its native table schema."""
        params = dict(params or {})
        if recipe == "daily_adjusted":
            params.setdefault("adjust", "qfq")
        return self._query([(source, recipe)], params, {"source": source, "recipe": recipe})

    def query(self, route: str, params: dict | None = None, recipe: str | None = None) -> dict:
        """Resolve a current ledger route. Ambiguous recipe lists require selection."""
        params = dict(params or {})
        history_routes = {"历史日线_不复权": ("stock", "d", "none"), "历史日线_复权": ("stock", "d", "qfq"),
                          "ETF行情": ("etf", "d", "none"), "指数行情": ("index", "d", "none"),
                          "分钟线": (None, "1m", "none")}
        if route in history_routes and recipe is None:
            asset, interval, adjust = history_routes[route]
            return self.history(params["symbol"], params["start"], params["end"],
                                params.get("interval", interval), params.get("adjust", adjust), params.get("asset", asset))
        db, _ = read_registry(self.root)
        spec = db["routing"].get(route)
        if not isinstance(spec, dict):
            raise ValueError("unknown_route")
        candidates = []
        first_recipe = None
        for sid in [spec.get("primary"), *spec.get("fallbacks", [])]:
            if not isinstance(sid, str):
                continue
            mapped = spec.get("recipe", {}).get(sid)
            if isinstance(mapped, list):
                if recipe is None:
                    raise ValueError("route_requires_explicit_recipe")
                mapped = recipe if recipe in mapped else None
            elif recipe and mapped != recipe:
                mapped = None
            if not mapped:
                continue
            if first_recipe is None:
                first_recipe = mapped
            # Distinct financial/index/macro recipes are not semantically interchangeable.
            equivalent = ({"quote_realtime", "quote_realtime_batch"}, {"trade_calendar", "trading_calendar"})
            if mapped != first_recipe and not any({mapped, first_recipe} <= group for group in equivalent):
                continue
            candidates.append((sid, mapped))
        return self._query(candidates, dict(params or {}), {"route": route, "recipe": recipe})

    def history(self, symbol: str, start: str, end: str, interval: str = "d", adjust: str = "none", asset: str | None = None) -> dict:
        """Get validated closed A-share/ETF/index bars, without filling gaps."""
        from .validation import history_params
        params = history_params(symbol, start, end, interval, adjust, asset)
        if interval != "d":
            route = "分钟线"
        elif params["asset"] == "etf":
            if adjust != "none":
                raise ValueError("etf_adjustment_not_supported")
            route = "ETF行情"
        elif params["asset"] == "index":
            if adjust != "none":
                raise ValueError("index_adjustment_not_applicable")
            route = "指数行情"
        else:
            route = "历史日线_不复权" if adjust == "none" else "历史日线_复权"
        db, _ = read_registry(self.root)
        spec = db["routing"][route]
        candidates = [(sid, spec.get("recipe", {}).get(sid)) for sid in [spec.get("primary"), *spec.get("fallbacks", [])]]
        candidates = [(sid, cap) for sid, cap in candidates if isinstance(sid, str) and isinstance(cap, str)]
        return self._query(candidates, params, {"route": route}, require_bars=True)

    def _query(self, candidates: list[tuple[str, str]], params: dict, request: dict, require_bars: bool = False) -> dict:
        db, digest = read_registry(self.root)
        envelope = {"status": "source_unavailable", "kind": None, "records": [], "metadata": {},
                    "source": None, "recipe": None, "attempts": [], "request": {**request, "params": params},
                    "registry_sha256": digest, "fetched_at": datetime.now(timezone.utc).isoformat()}
        if not self._runtime_ready(db):
            return {**envelope, "status": "error", "reason": "active_environment_missing"}
        deadline = time.monotonic() + self.timeout
        for sid, cap in candidates:
            reason = unavailable(db, sid, cap)
            if reason:
                envelope["attempts"].append({"source": sid, "recipe": cap, "status": "skipped", "reason": reason})
                continue
            left = deadline - time.monotonic()
            if left < 1:
                envelope["attempts"].append({"source": sid, "recipe": cap, "status": "error", "reason": "request_deadline"})
                break
            # Reserve time for a fallback instead of letting one provider consume all time.
            seconds = min(60, left)
            try:
                result = self._run({"root": str(self.root), "source": sid, "recipe": cap, "params": params,
                                    "require_bars": require_bars, "registry_sha256": digest}, seconds)
            except DataSourceError as exc:
                result = {"status": "error", "reason": str(exc)}
            status = result.get("status", "error")
            envelope["attempts"].append({"source": sid, "recipe": cap, "status": status, "reason": result.get("reason")})
            if result.get("reason") == "provider_cleanup_failed":
                return {**envelope, "status": "error", "reason": "provider_cleanup_failed"}
            if status == "ok":
                return {**envelope, **result, "source": sid, "recipe": cap,
                        "fetched_at": datetime.now(timezone.utc).isoformat()}
            if status == "no_data":
                envelope["status"] = "no_data"
            elif envelope["status"] != "no_data":
                envelope["status"] = status
        if not candidates:
            envelope.update(status="unsupported", reason="no_compatible_recipe")
        return envelope

    def _run(self, payload: dict, timeout: float) -> dict:
        try:
            request_data = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError):
            raise DataSourceError("invalid_request_payload") from None
        env = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME"):
            env.pop(key, None)
        env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        args = [sys.executable, str(self.root / "registry" / "ds.py"), "run", "--",
                str(Path(__file__).with_name("worker.py"))]
        try:
            process = subprocess.Popen(args, cwd=self.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                       env=env, creationflags=flags, start_new_session=os.name != "nt")
        except OSError:
            raise DataSourceError("worker_start_failed") from None
        try:
            stdout, _ = process.communicate(request_data, timeout=timeout)
        except subprocess.TimeoutExpired:
            cleanup_failed = False
            try:
                if os.name == "nt":
                    killed = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, timeout=15)
                    cleanup_failed = killed.returncode != 0
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failed = True
            finally:
                try:
                    if cleanup_failed:
                        process.kill()
                    process.communicate(timeout=15)
                except (OSError, subprocess.TimeoutExpired):
                    cleanup_failed = True
            raise DataSourceError("provider_cleanup_failed" if cleanup_failed else "provider_timeout") from None
        if process.returncode:
            # Raw provider output may contain credentials. It never leaves this boundary.
            raise DataSourceError("worker_process_failed")
        try:
            result = json.loads(stdout)
            if not isinstance(result, dict) or result.get("status") not in {"ok", "no_data", "unsupported", "source_unavailable", "error"}:
                raise ValueError
            if result.get("status") == "ok" and not isinstance(result.get("records"), list):
                raise ValueError
            return result
        except (ValueError, TypeError):
            raise DataSourceError("invalid_worker_response") from None
