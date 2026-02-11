"""WinOCR 기반 OCR 엔진."""

from __future__ import annotations

import time

import numpy as np

from aion2meter.models import OcrResult


class WinOcrEngine:
    """Windows OCR(winocr)을 사용하는 OCR 엔진.

    OcrEngine Protocol 구현.
    """

    def recognize(self, image: np.ndarray) -> OcrResult:
        """이미지에서 텍스트를 인식한다."""
        try:
            import winocr  # type: ignore[import-untyped]
        except ImportError:
            raise RuntimeError("winocr not available")

        result = winocr.recognize_cv2_sync(image, lang="ko")
        timestamp = time.time()
        text = result.get("text", "") if isinstance(result, dict) else str(result)
        confidence = float(result.get("confidence", 0.0)) if isinstance(result, dict) else 0.0

        return OcrResult(text=text, confidence=confidence, timestamp=timestamp)
