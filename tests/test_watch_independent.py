# -*- coding: utf-8 -*-
"""关注航班是独立实体：只按本地落库数据过滤匹配，不绑定配置航线。"""
import pytest

import webui


def payload(**kw):
    data = {
        "from": "SHA", "to": "BJS", "date": "2026-11-01",
        "code": "MU5101", "depTime": "08:00", "arrTime": "10:00",
        "channels": ["qunar"],
    }
    data.update(kw)
    return data


def test_watch_accepts_independent_date_and_channels(monkeypatch):
    user = {"name": "u", "platforms": ["qunar"],
            "routes": [{"from": "SHA", "to": "BJS", "dates": ["2026-11-01"]}]}
    monkeypatch.setattr(webui._State, "users", [user])
    entry = webui._watch_entry(
        payload(date="2027-01-09", channels=["ctrip", "tongcheng"]), user="u")
    assert entry["date"] == "2027-01-09"
    assert entry["channels"] == ["ctrip", "tongcheng"]


def test_watch_defaults_to_all_scan_channels(monkeypatch):
    monkeypatch.setattr(webui._State, "users", [])
    entry = webui._watch_entry(payload(channels=None))
    assert entry["channels"] == list(webui._WATCH_PLATS)


def test_watch_scope_is_date_only(monkeypatch):
    user = {"name": "u", "platforms": ["qunar"], "routes": []}
    monkeypatch.setattr(webui._State, "users", [user])
    entry = webui._watch_entry(payload())
    public = webui._watch_public(entry, "u")
    assert public["inScope"] is True
    assert public["scopeReason"] == ""

    entry["date"] = "2020-01-01"
    public = webui._watch_public(entry, "u")
    assert public["inScope"] is False
    assert "日期" in public["scopeReason"]


def test_watch_preview_keeps_free_form(monkeypatch):
    monkeypatch.setattr(webui._State, "users", [])
    entry = webui._watch_entry(payload(date="2027-01-09", channels=["tongcheng"]))
    assert entry["channels"] == ["tongcheng"]
