"""Tesseract 기반 OCR 엔진."""

from __future__ import annotations

import time

import numpy as np

from aion2meter.models import OcrResult


class TesseractEngine:
    """pytesseract를 사용하는 OCR 엔진.

    OcrEngine Protocol 구현.
    """

    def recognize(self, image: np.ndarray) -> OcrResult:
        """이미지에서 텍스트를 인식한다."""
        try:
            import pytesseract  # type: ignore[import-untyped]
        except ImportError:
            raise RuntimeError("pytesseract not available")

        timestamp = time.time()
        text = pytesseract.image_to_string(image, lang="kor", config="--psm 6 --oem 3")

        return OcrResult(text=text.strip(), confidence=0.0, timestamp=timestamp)
