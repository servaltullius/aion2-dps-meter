"""HotkeyManager 단위 테스트."""

from __future__ import annotations

from aion2meter.hotkey_manager import HotkeyManager


class TestHotkeyManager:
    """HotkeyManager 기본 동작."""

    def test_create_instance(self):
        mgr = HotkeyManager()
        assert mgr is not None

    def test_register_and_unregister(self):
        mgr = HotkeyManager()
        called = []
        mgr.register("<ctrl>+<shift>+t", lambda: called.append(1))
        mgr.unregister_all()
        assert mgr._hotkeys == {}

    def test_register_multiple(self):
        mgr = HotkeyManager()
        mgr.register("<ctrl>+<shift>+a", lambda: None)
        mgr.register("<ctrl>+<shift>+b", lambda: None)
        assert len(mgr._hotkeys) == 2

    def test_register_overwrites_same_key(self):
        mgr = HotkeyManager()
        mgr.register("<ctrl>+<shift>+a", lambda: None)
        mgr.register("<ctrl>+<shift>+a", lambda: None)
        assert len(mgr._hotkeys) == 1

    def test_empty_hotkey_string_ignored(self):
        mgr = HotkeyManager()
        mgr.register("", lambda: None)
        assert mgr._hotkeys == {}

    def test_stop_without_start(self):
        mgr = HotkeyManager()
        mgr.stop()  # should not raise
