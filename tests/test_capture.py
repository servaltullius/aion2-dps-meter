"""화면 캡처 단위 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from aion2meter.capture.mss_capture import MssCapture
from aion2meter.capture.roi import validate_roi
from aion2meter.models import ROI


class TestValidateRoi:
    """validate_roi 테스트."""

    def test_valid_roi(self) -> None:
        roi = ROI(left=0, top=0, width=800, height=600)
        assert validate_roi(roi, screen_width=1920, screen_height=1080) is True

    def test_exact_boundary(self) -> None:
        """ROI가 화면 경계에 정확히 맞을 때 유효하다."""
        roi = ROI(left=1120, top=480, width=800, height=600)
        assert validate_roi(roi, screen_width=1920, screen_height=1080) is True

    def test_exceeds_width(self) -> None:
        """ROI가 화면 너비를 초과하면 무효하다."""
        roi = ROI(left=1200, top=0, width=800, height=600)
        assert validate_roi(roi, screen_width=1920, screen_height=1080) is False

    def test_exceeds_height(self) -> None:
        """ROI가 화면 높이를 초과하면 무효하다."""
        roi = ROI(left=0, top=600, width=800, height=600)
        assert validate_roi(roi, screen_width=1920, screen_height=1080) is False

    def test_exceeds_both(self) -> None:
        """ROI가 너비와 높이 모두 초과하면 무효하다."""
        roi = ROI(left=1500, top=900, width=800, height=600)
        assert validate_roi(roi, screen_width=1920, screen_height=1080) is False


class TestMssCapture:
    """MssCapture 테스트 (mss mock)."""

    def test_capture_returns_captured_frame(self) -> None:
        """capture()는 CapturedFrame을 반환한다."""
        roi = ROI(left=0, top=0, width=100, height=50)

        # BGRA 이미지 시뮬레이션 (50 x 100 x 4)
        fake_bgra = np.zeros((50, 100, 4), dtype=np.uint8)
        fake_bgra[:, :, 0] = 10  # B
        fake_bgra[:, :, 1] = 20  # G
        fake_bgra[:, :, 2] = 30  # R
        fake_bgra[:, :, 3] = 255  # A

        mock_sct_instance = MagicMock()
        mock_sct_instance.grab.return_value = fake_bgra

        with patch("aion2meter.capture.mss_capture.mss.mss") as mock_mss:
            mock_mss.return_value.__enter__ = MagicMock(return_value=mock_sct_instance)
            mock_mss.return_value.__exit__ = MagicMock(return_value=False)

            capturer = MssCapture()
            frame = capturer.capture(roi)

        assert frame.roi == roi
        assert frame.timestamp > 0

        image: np.ndarray = frame.image  # type: ignore[assignment]
        # BGRA -> BGR: 채널 3개
        assert image.shape == (50, 100, 3)
        assert image[0, 0, 0] == 10  # B
        assert image[0, 0, 1] == 20  # G
        assert image[0, 0, 2] == 30  # R

    def test_capture_calls_grab_with_roi_dict(self) -> None:
        """capture()는 mss.grab에 ROI dict를 전달한다."""
        roi = ROI(left=100, top=200, width=300, height=400)
        fake_bgra = np.zeros((400, 300, 4), dtype=np.uint8)

        mock_sct_instance = MagicMock()
        mock_sct_instance.grab.return_value = fake_bgra

        with patch("aion2meter.capture.mss_capture.mss.mss") as mock_mss:
            mock_mss.return_value.__enter__ = MagicMock(return_value=mock_sct_instance)
            mock_mss.return_value.__exit__ = MagicMock(return_value=False)

            capturer = MssCapture()
            capturer.capture(roi)

        mock_sct_instance.grab.assert_called_once_with(
            {"left": 100, "top": 200, "width": 300, "height": 400}
        )
