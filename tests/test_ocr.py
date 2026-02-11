"""OCR 엔진 매니저 단위 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from aion2meter.models import OcrResult
from aion2meter.ocr.engine_manager import OcrEngineManager


def _ok_result(text: str = "테스트") -> OcrResult:
    return OcrResult(text=text, confidence=0.95, timestamp=1.0)


def _make_image() -> np.ndarray:
    return np.zeros((10, 20, 3), dtype=np.uint8)


class TestOcrEngineManager:
    """OcrEngineManager 테스트."""

    def test_primary_success(self) -> None:
        """Primary 엔진이 정상이면 그 결과를 반환한다."""
        primary = MagicMock()
        primary.recognize.return_value = _ok_result("primary")

        mgr = OcrEngineManager(primary=primary)
        result = mgr.recognize(_make_image())

        assert result.text == "primary"
        primary.recognize.assert_called_once()

    def test_primary_fail_returns_empty_before_max(self) -> None:
        """Primary가 실패해도 max_failures 미만이면 빈 결과를 반환한다."""
        primary = MagicMock()
        primary.recognize.side_effect = RuntimeError("fail")
        fallback = MagicMock()
        fallback.recognize.return_value = _ok_result("fallback")

        mgr = OcrEngineManager(primary=primary, fallback=fallback, max_failures=3)

        # 1회 실패: 아직 fallback 전환 안 됨
        result = mgr.recognize(_make_image())
        assert result.text == ""
        fallback.recognize.assert_not_called()

    def test_switch_to_fallback_after_max_failures(self) -> None:
        """max_failures 회 연속 실패하면 fallback으로 전환한다."""
        primary = MagicMock()
        primary.recognize.side_effect = RuntimeError("fail")
        fallback = MagicMock()
        fallback.recognize.return_value = _ok_result("fallback")

        mgr = OcrEngineManager(primary=primary, fallback=fallback, max_failures=3)
        image = _make_image()

        # 1, 2회: 빈 결과
        mgr.recognize(image)
        mgr.recognize(image)

        # 3회: max_failures 도달 -> fallback 전환
        result = mgr.recognize(image)
        assert result.text == "fallback"

    def test_fallback_also_fails(self) -> None:
        """Fallback도 실패하면 빈 결과를 반환한다."""
        primary = MagicMock()
        primary.recognize.side_effect = RuntimeError("primary fail")
        fallback = MagicMock()
        fallback.recognize.side_effect = RuntimeError("fallback fail")

        mgr = OcrEngineManager(primary=primary, fallback=fallback, max_failures=1)
        image = _make_image()

        # max_failures=1이므로 1회 실패 후 즉시 fallback 전환
        result = mgr.recognize(image)
        assert result.text == ""
        assert result.confidence == 0.0

    def test_no_fallback_after_max_failures(self) -> None:
        """Fallback이 없고 max_failures 초과하면 빈 결과를 반환한다."""
        primary = MagicMock()
        primary.recognize.side_effect = RuntimeError("fail")

        mgr = OcrEngineManager(primary=primary, fallback=None, max_failures=2)
        image = _make_image()

        mgr.recognize(image)
        result = mgr.recognize(image)
        assert result.text == ""

    def test_failure_count_resets_on_success(self) -> None:
        """Primary가 성공하면 실패 카운트가 초기화된다."""
        primary = MagicMock()
        primary.recognize.side_effect = [
            RuntimeError("fail"),
            _ok_result("ok"),
            RuntimeError("fail"),
            RuntimeError("fail"),
            _ok_result("ok again"),
        ]

        mgr = OcrEngineManager(primary=primary, fallback=None, max_failures=3)
        image = _make_image()

        mgr.recognize(image)       # fail (count=1)
        result = mgr.recognize(image)  # ok (count=0)
        assert result.text == "ok"

        mgr.recognize(image)       # fail (count=1)
        mgr.recognize(image)       # fail (count=2)
        result = mgr.recognize(image)  # ok (count=0)
        assert result.text == "ok again"


class TestBestConfidenceMode:
    """best_confidence 모드 테스트."""

    def test_best_confidence_picks_higher(self) -> None:
        """두 엔진 중 confidence가 높은 쪽을 선택한다."""
        primary = MagicMock()
        primary.recognize.return_value = OcrResult(text="primary", confidence=0.7, timestamp=1.0)
        fallback = MagicMock()
        fallback.recognize.return_value = OcrResult(text="fallback", confidence=0.9, timestamp=1.0)

        mgr = OcrEngineManager(primary=primary, fallback=fallback, mode="best_confidence")
        result = mgr.recognize(_make_image())

        assert result.text == "fallback"
        assert result.confidence == 0.9

    def test_best_confidence_primary_wins(self) -> None:
        """primary의 confidence가 높으면 primary를 선택한다."""
        primary = MagicMock()
        primary.recognize.return_value = OcrResult(text="primary", confidence=0.95, timestamp=1.0)
        fallback = MagicMock()
        fallback.recognize.return_value = OcrResult(text="fallback", confidence=0.8, timestamp=1.0)

        mgr = OcrEngineManager(primary=primary, fallback=fallback, mode="best_confidence")
        result = mgr.recognize(_make_image())

        assert result.text == "primary"

    def test_best_confidence_fallback_error(self) -> None:
        """best_confidence 모드에서 fallback이 에러나면 primary 결과를 사용한다."""
        primary = MagicMock()
        primary.recognize.return_value = OcrResult(text="primary", confidence=0.7, timestamp=1.0)
        fallback = MagicMock()
        fallback.recognize.side_effect = RuntimeError("fail")

        mgr = OcrEngineManager(primary=primary, fallback=fallback, mode="best_confidence")
        result = mgr.recognize(_make_image())

        assert result.text == "primary"

    def test_best_confidence_no_fallback(self) -> None:
        """fallback 없이 best_confidence 모드면 primary만 사용한다."""
        primary = MagicMock()
        primary.recognize.return_value = OcrResult(text="primary", confidence=0.7, timestamp=1.0)

        mgr = OcrEngineManager(primary=primary, fallback=None, mode="best_confidence")
        result = mgr.recognize(_make_image())

        assert result.text == "primary"
