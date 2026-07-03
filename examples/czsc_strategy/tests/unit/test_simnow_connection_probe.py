import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_connection_probe import mask_setting, validate_config  # noqa: E402


def test_mask_setting_hides_sensitive_fields():
    masked = mask_setting({
        "用户名": "12345678",
        "密码": "secret",
        "交易服务器": "tcp://host:1",
        "授权编码": "abcdef",
    })
    assert masked["用户名"] == "12***78"
    assert masked["密码"] == "se***et"
    assert masked["授权编码"] == "ab***ef"
    assert masked["交易服务器"] == "tcp://host:1"


def test_validate_config_reports_missing_required_fields():
    problems = validate_config({"setting": {"用户名": "u"}, "subscribe": [{"symbol": "ap610"}]})
    assert "missing setting field: 密码" in problems
    assert "missing setting field: 交易服务器" in problems
    assert "subscribe[0] missing exchange" in problems


def test_validate_config_accepts_minimal_complete_config():
    problems = validate_config({
        "setting": {
            "用户名": "u",
            "密码": "p",
            "经纪商代码": "9999",
            "交易服务器": "tcp://td:1",
            "行情服务器": "tcp://md:1",
            "产品名称": "app",
            "授权编码": "auth",
            "柜台环境": "测试",
        },
        "subscribe": [{"symbol": "ap610", "exchange": "CZCE"}],
    })
    assert problems == []
