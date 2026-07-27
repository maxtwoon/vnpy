import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_structured_access import safe_get  # noqa: E402


def test_safe_get_walks_nested_dicts():
    assert safe_get({"a": {"b": {"c": 1}}}, "a", "b", "c", default=0) == 1


def test_safe_get_returns_default_for_missing_key():
    assert safe_get({"a": {}}, "a", "b", default="x") == "x"


def test_safe_get_returns_default_when_path_hits_nondict():
    assert safe_get({"a": 1}, "a", "b", default="x") == "x"
