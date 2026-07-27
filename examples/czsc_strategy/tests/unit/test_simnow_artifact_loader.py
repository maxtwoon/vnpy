import json
import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_artifact_loader import load_json_dict  # noqa: E402
from simnow_artifact_loader import load_jsonl_records  # noqa: E402


def test_load_json_dict_returns_empty_for_missing_file(tmp_path):
    assert load_json_dict(tmp_path / "missing.json") == {}


def test_load_json_dict_reads_utf8_sig_json(tmp_path):
    path = tmp_path / "sample.json"
    path.write_text(json.dumps({"status": "ok"}), encoding="utf-8-sig")

    assert load_json_dict(path) == {"status": "ok"}


def test_load_jsonl_records_returns_empty_for_missing_file(tmp_path):
    assert load_jsonl_records(tmp_path / "missing.jsonl") == []


def test_load_jsonl_records_reads_utf8_sig_jsonl(tmp_path):
    path = tmp_path / "sample.jsonl"
    path.write_text('{"status":"ok"}\n{"status":"next"}\n', encoding="utf-8-sig")

    assert load_jsonl_records(path) == [{"status": "ok"}, {"status": "next"}]


def test_load_jsonl_records_reads_plain_utf8_jsonl(tmp_path):
    path = tmp_path / "sample_utf8.jsonl"
    path.write_text('{"status":"ok"}\n{"status":"next"}\n', encoding="utf-8")

    assert load_jsonl_records(path) == [{"status": "ok"}, {"status": "next"}]
