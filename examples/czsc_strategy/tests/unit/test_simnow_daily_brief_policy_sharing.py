import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))


def test_daily_brief_imports_shared_automation_policy_instead_of_defining_local_copy():
    import simnow_daily_brief as brief_mod

    src = Path(brief_mod.__file__).read_text(encoding="utf-8")
    assert "from simnow_artifact_loader import" in src
    assert "from simnow_automation_policy import" in src
    assert "def _build_record_for_action" not in src
    assert "def _legacy_conclusion_text" not in src
    assert "def _resolve_action_meta" not in src
    assert "def needs_user_action" not in src
    assert "def _conclusion_text" not in src


def test_daily_brief_schema_and_automation_policy_import_shared_safe_get():
    import simnow_automation_policy as policy_mod
    import simnow_daily_brief_schema as schema_mod

    policy_src = Path(policy_mod.__file__).read_text(encoding="utf-8")
    schema_src = Path(schema_mod.__file__).read_text(encoding="utf-8")

    assert "from simnow_structured_access import safe_get" in policy_src
    assert "from simnow_structured_access import safe_get" in schema_src
