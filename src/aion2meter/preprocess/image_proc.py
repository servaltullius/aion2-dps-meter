"""전투 로그 이미지 전처리."""

from __future__ import annotations

import hashlib

import cv2
import numpy as np

from aion2meter.models import AppConfig, CapturedFrame, ColorRange


class CombatLogPreprocessor:
    """캡처된 프레임을 OCR에 적합한 이진 이미지로 전처리한다.

    ImagePreprocessor Protocol 구현.
    """

    def __init__(self, color_ranges: list[ColorRange] | None = None) -> None:
        self._color_ranges = color_ranges or AppConfig.default_color_ranges()
        self._prev_hash: str | None = None

    def process(self, frame: CapturedFrame) -> np.ndarray:
        """프레임을 전처리하여 이진화된 numpy 배열을 반환한다.

        1. 2x 업스케일 (INTER_NEAREST_EXACT)
        2. 각 ColorRange에 대해 inRange 마스크 생성
        3. 모든 마스크 OR 결합
        4. 이진화: 마스크가 있는 곳은 흰색, 없는 곳은 검은색
        """
        image: np.ndarray = frame.image  # type: ignore[assignment]
        h, w = image.shape[:2]

        # 1) 2x 업스케일
        upscaled = cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_NEAREST_EXACT)

        # 2-3) 색상 범위별 마스크 생성 후 OR 결합
        combined_mask = np.zeros(upscaled.shape[:2], dtype=np.uint8)
        for cr in self._color_ranges:
            lower = np.array(cr.lower, dtype=np.uint8)
            upper = np.array(cr.upper, dtype=np.uint8)
            mask = cv2.inRange(upscaled, lower, upper)
            combined_mask = cv2.bitwise_or(combined_mask, mask)

        # 4) 이진화: 마스크가 있는 곳 흰색(255), 없는 곳 검은색(0)
        binary = np.where(combined_mask > 0, np.uint8(255), np.uint8(0)).astype(np.uint8)
        return binary

    def is_duplicate(self, frame: CapturedFrame) -> bool:
        """이전 프레임과 동일한지 MD5 해시로 비교한다."""
        image: np.ndarray = frame.image  # type: ignore[assignment]
        current_hash = hashlib.md5(image.tobytes()).hexdigest()
        if self._prev_hash is not None and current_hash == self._prev_hash:
            return True
        self._prev_hash = current_hash
        return False
