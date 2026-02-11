"""글로벌 키보드 단축키 관리자."""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


class HotkeyManager:
    """pynput 기반 글로벌 핫키 관리자.

    pynput이 설치되지 않은 환경에서도 에러 없이 동작한다 (기능 비활성).
    """

    def __init__(self) -> None:
        self._hotkeys: dict[str, Callable] = {}
        self._listener: object | None = None

    def register(self, hotkey: str, callback: Callable) -> None:
        """핫키를 등록한다. 빈 문자열은 무시."""
        if not hotkey:
            return
        self._hotkeys[hotkey] = callback

    def unregister_all(self) -> None:
        """모든 핫키를 해제한다."""
        self._hotkeys = {}

    def start(self) -> None:
        """핫키 리스너를 시작한다."""
        if not self._hotkeys:
            return
        try:
            from pynput.keyboard import GlobalHotKeys
            self._listener = GlobalHotKeys(self._hotkeys)
            self._listener.start()
            logger.info("핫키 리스너 시작: %s", list(self._hotkeys.keys()))
        except ImportError:
            logger.warning("pynput 미설치 — 단축키 비활성")
        except Exception:
            logger.warning("핫키 리스너 시작 실패", exc_info=True)

    def stop(self) -> None:
        """핫키 리스너를 종료한다."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
