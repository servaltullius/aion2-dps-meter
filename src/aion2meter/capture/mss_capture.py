"""mss 기반 화면 캡처."""

from __future__ import annotations

import time

import mss
import numpy as np

from aion2meter.models import CapturedFrame, ROI


class MssCapture:
    """mss를 이용한 화면 캡처.

    ScreenCapturer Protocol 구현.
    """

    def capture(self, roi: ROI) -> CapturedFrame:
        """지정된 ROI 영역을 캡처하여 CapturedFrame을 반환한다."""
        with mss.mss() as sct:
            raw = sct.grab(roi.as_dict())
            # BGRA -> BGR: 알파 채널 제거
            image = np.array(raw)[:, :, :3]
            return CapturedFrame(
                image=image,
                timestamp=time.time(),
                roi=roi,
            )
