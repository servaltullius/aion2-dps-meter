"""OCR 엔진 장애 복구 관리자."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aion2meter.models import OcrResult

if TYPE_CHECKING:
    import numpy as np

    from aion2meter.protocols import OcrEngine

logger = logging.getLogger(__name__)


class OcrEngineManager:
    """Primary/fallback OCR 엔진을 관리하며 장애 시 자동 전환한다.

    OcrEngine Protocol 구현.
    """

    def __init__(
        self,
        primary: OcrEngine,
        fallback: OcrEngine | None = None,
        max_failures: int = 3,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._max_failures = max_failures
        self._failure_count: int = 0
        self._using_fallback: bool = False

    def recognize(self, image: np.ndarray) -> OcrResult:
        """이미지에서 텍스트를 인식한다.

        Primary 엔진으로 시도하고, 연속 실패가 max_failures를 초과하면
        fallback 엔진으로 전환한다.
        """
        if not self._using_fallback:
            try:
                result = self._primary.recognize(image)
                self._failure_count = 0
                return result
            except Exception:
                self._failure_count += 1
                logger.warning(
                    "primary OCR 실패 (%d/%d)", self._failure_count, self._max_failures
                )
                if self._failure_count >= self._max_failures:
                    if self._fallback is not None:
                        logger.warning("fallback OCR 엔진으로 전환")
                        self._using_fallback = True
                    else:
                        return self._empty_result()
                else:
                    return self._empty_result()

        # fallback 시도
        if self._fallback is not None:
            try:
                return self._fallback.recognize(image)
            except Exception:
                logger.warning("fallback OCR도 실패")
                return self._empty_result()

        return self._empty_result()

    @staticmethod
    def _empty_result() -> OcrResult:
        return OcrResult(text="", confidence=0.0, timestamp=0.0)
