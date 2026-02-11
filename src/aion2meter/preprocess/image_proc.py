"""전투 로그 이미지 전처리."""

from __future__ import annotations

import cv2
import numpy as np

from aion2meter.models import AppConfig, CapturedFrame, ColorRange, PreprocessConfig


class CombatLogPreprocessor:
    """캡처된 프레임을 OCR에 적합한 이진 이미지로 전처리한다.

    ImagePreprocessor Protocol 구현.
    """

    def __init__(
        self,
        color_ranges: list[ColorRange] | None = None,
        preprocess_config: PreprocessConfig | None = None,
    ) -> None:
        self._color_ranges = color_ranges or AppConfig.default_color_ranges()
        self._config = preprocess_config or PreprocessConfig()
        self._prev_hash: tuple | None = None

    def process(self, frame: CapturedFrame) -> np.ndarray:
        """프레임을 전처리하여 이진화된 numpy 배열을 반환한다.

        파이프라인: upscale → denoise → sharpen → color_mask → binary → cleanup
        """
        image: np.ndarray = frame.image  # type: ignore[assignment]
        h, w = image.shape[:2]

        # 1) 업스케일
        factor = self._config.upscale_factor
        upscaled = cv2.resize(
            image, (w * factor, h * factor), interpolation=cv2.INTER_NEAREST_EXACT,
        )

        # 2) Denoise (morphological open + close)
        if self._config.denoise:
            upscaled = self._denoise(upscaled)

        # 3) Sharpen (unsharp mask)
        if self._config.sharpen:
            upscaled = self._sharpen(upscaled)

        # 4) 색상 범위별 마스크 생성 후 OR 결합
        combined_mask = np.zeros(upscaled.shape[:2], dtype=np.uint8)
        for cr in self._color_ranges:
            lower = np.array(cr.lower, dtype=np.uint8)
            upper = np.array(cr.upper, dtype=np.uint8)
            mask = cv2.inRange(upscaled, lower, upper)
            combined_mask = cv2.bitwise_or(combined_mask, mask)

        # 5) 이진화
        binary = np.where(combined_mask > 0, np.uint8(255), np.uint8(0)).astype(np.uint8)

        # 6) Cleanup (작은 컴포넌트 제거)
        if self._config.cleanup_min_area > 0:
            binary = self._cleanup(binary, self._config.cleanup_min_area)

        return binary

    @staticmethod
    def _denoise(image: np.ndarray) -> np.ndarray:
        """모폴로지 연산으로 노이즈를 제거한다."""
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        opened = cv2.morphologyEx(image, cv2.MORPH_OPEN, kernel)
        closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel)
        return closed

    @staticmethod
    def _sharpen(image: np.ndarray) -> np.ndarray:
        """Unsharp mask로 이미지를 샤프닝한다."""
        blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=1.0)
        sharpened = cv2.addWeighted(image, 1.5, blurred, -0.5, 0)
        return sharpened

    @staticmethod
    def _cleanup(binary: np.ndarray, min_area: int) -> np.ndarray:
        """min_area 미만의 연결 컴포넌트를 제거한다."""
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        result = np.zeros_like(binary)
        for i in range(1, num_labels):  # 0은 배경
            if stats[i, cv2.CC_STAT_AREA] >= min_area:
                result[labels == i] = 255
        return result

    def is_duplicate(self, frame: CapturedFrame) -> bool:
        """이전 프레임과 동일한지 5지점 픽셀 샘플링으로 비교한다."""
        image: np.ndarray = frame.image  # type: ignore[assignment]
        h, w = image.shape[:2]
        if h == 0 or w == 0:
            return False

        points = [
            (0, 0),
            (0, w - 1),
            (h - 1, 0),
            (h - 1, w - 1),
            (h // 2, w // 2),
        ]
        sample = tuple(image[y, x].tobytes() for y, x in points)

        if self._prev_hash is not None and sample == self._prev_hash:
            return True
        self._prev_hash = sample
        return False
