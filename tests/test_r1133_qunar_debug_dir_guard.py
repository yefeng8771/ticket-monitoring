# -*- coding: utf-8 -*-
"""r1133：debug/token 落盘目录建不出来时不得中断采集（issue #15）。

用户把 debug_dir 配成空串时，`os.makedirs("")` 抛 FileNotFoundError；
旧代码把它放在 try 外，整轮采集当场崩（Win 实测堆栈停在
`crawlers/qunar.py::_dump_raw_text`）。调试落盘是旁路：建目录失败
只能丢 dump，不能把已经拿到的价格结果带走；token 保存同理。
"""
import logging

from crawlers.qunar import QunarCrawler

_LOG = logging.getLogger("r1133")


def _crawler():
    return QunarCrawler({"delay_min": 0, "delay_max": 0}, _LOG)


def test_unwritable_debug_dir_does_not_break_collection():
    q = _crawler()
    q.debug = True
    q.debug_dir = ""  # issue #15 诱因：空串让 makedirs 抛 FileNotFoundError
    q._dump_raw_text('{"ok":1}', "probe")


def test_unwritable_token_dir_does_not_break_save(tmp_path):
    q = _crawler()
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    q.user_data_root = str(blocker / "sub")
    q._save_token({"headers": {}, "body_template": "", "cookies": []})


def test_debug_dump_still_written_when_dir_is_valid(tmp_path):
    q = _crawler()
    q.debug = True
    q.debug_dir = str(tmp_path / "dbg")
    q._dump_raw_text('{"ok":1}', "t1")
    p = tmp_path / "dbg" / "qunar_raw_t1.txt"
    assert p.read_text(encoding="utf-8") == '{"ok":1}'
