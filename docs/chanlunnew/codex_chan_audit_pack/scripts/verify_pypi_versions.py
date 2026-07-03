#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网验证 PyPI czsc 版本事实。

如果当前机器不能联网，此脚本会给出无法验证提示。
"""
from __future__ import annotations
import json
import re
import urllib.request

urls = {
    "json": "https://pypi.org/pypi/czsc/json",
    "simple": "https://pypi.org/simple/czsc/",
}

try:
    with urllib.request.urlopen(urls["json"], timeout=20) as r:
        data = json.load(r)
    releases = sorted(data.get("releases", {}).keys())
    rc_1 = [v for v in releases if v.startswith("1.0.0rc")]
    latest = data.get("info", {}).get("version")
    print(json.dumps({"ok": True, "latest_json_version": latest, "has_1_0_rc": bool(rc_1), "rc_versions": rc_1[-10:], "n_releases": len(releases)}, ensure_ascii=False, indent=2))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e), "hint": "无法联网或 PyPI 不可访问；请手动检查 https://pypi.org/project/czsc/ 与 https://pypi.org/simple/czsc/"}, ensure_ascii=False, indent=2))
