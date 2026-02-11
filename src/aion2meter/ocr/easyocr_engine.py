"""EasyOCR 기반 OCR 엔진."""

from __future__ import annotations

import time

import numpy as np

from aion2meter.models import OcrResult


class EasyOcrEngine:
    """EasyOCR을 사용하는 OCR 엔진.

    OcrEngine Protocol 구현. reader는 첫 recognize() 호출 시 lazy init.
    """

    def __init__(self, gpu: bool = True, lang: list[str] | None = None) -> None:
        self._reader: object | None = None
        self._gpu = gpu
        self._lang = lang or ["ko", "en"]

    def _ensure_reader(self) -> None:
        """reader가 없으면 생성한다."""
        if self._reader is not None:
            return
        try:
            import easyocr  # type: ignore[import-untyped]
        except ImportError:
            raise RuntimeError("easyocr not available. Install with: pip install easyocr")
        self._reader = easyocr.Reader(self._lang, gpu=self._gpu)

    def recognize(self, image: np.ndarray) -> OcrResult:
        """이미지에서 텍스트를 인식한다."""
        self._ensure_reader()
        results = self._reader.readtext(image)  # type: ignore[union-attr]
        timestamp = time.time()

        if not results:
            return OcrResult(text="", confidence=0.0, timestamp=timestamp)

        text = "\n".join(r[1] for r in results)
        avg_confidence = sum(r[2] for r in results) / len(results)

        return OcrResult(text=text, confidence=avg_confidence, timestamp=timestamp)
