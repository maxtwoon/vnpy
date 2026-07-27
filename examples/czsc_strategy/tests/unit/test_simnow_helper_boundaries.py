import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))


def _read(name: str) -> str:
    return (DIAG / name).read_text(encoding="utf-8")


def test_shared_loader_boundaries_stay_centralized():
    daily_brief_src = _read("simnow_daily_brief.py")
    run_summary_src = _read("simnow_run_summary.py")
    ledger_summary_src = _read("simnow_ledger_summary.py")
    artifact_loader_src = _read("simnow_artifact_loader.py")

    assert "from simnow_artifact_loader import load_json_dict" in daily_brief_src
    assert "from simnow_artifact_loader import load_json_dict, load_jsonl_records" in run_summary_src
    assert "from simnow_artifact_loader import load_jsonl_records" in ledger_summary_src
    assert artifact_loader_src.count("def load_json_dict(") == 1
    assert artifact_loader_src.count("def load_jsonl_records(") == 1


def test_shared_safe_get_boundary_stays_centralized():
    structured_access_src = _read("simnow_structured_access.py")
    automation_policy_src = _read("simnow_automation_policy.py")
    daily_brief_schema_src = _read("simnow_daily_brief_schema.py")

    assert structured_access_src.count("def safe_get(") == 1
    assert "from simnow_structured_access import safe_get" in automation_policy_src
    assert "from simnow_structured_access import safe_get" in daily_brief_schema_src
    assert "def _safe_get(" not in automation_policy_src
    assert "def safe_get(" not in automation_policy_src
    assert "def safe_get(" not in daily_brief_schema_src
