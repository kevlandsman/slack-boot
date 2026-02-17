from __future__ import annotations

import importlib
import sys


def test_main_import_creates_log_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    sys.modules.pop("main", None)
    importlib.import_module("main")
    assert (tmp_path / ".slack-booty").exists()
