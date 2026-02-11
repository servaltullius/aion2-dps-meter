"""이미지 전처리 단위 테스트."""

from __future__ import annotations

import numpy as np

from aion2meter.models import CapturedFrame, ColorRange, ROI
from aion2meter.preprocess.image_proc import CombatLogPreprocessor


def _make_frame(image: np.ndarray) -> CapturedFrame:
    """테스트용 CapturedFrame을 생성한다."""
    return CapturedFrame(
        image=image,
        timestamp=0.0,
        roi=ROI(left=0, top=0, width=image.shape[1], height=image.shape[0]),
    )


class TestCombatLogPreprocessor:
    """CombatLogPreprocessor 테스트."""

    def test_process_returns_2x_size(self) -> None:
        """process()는 원본의 2배 크기 이미지를 반환한다."""
        image = np.zeros((50, 100, 3), dtype=np.uint8)
        frame = _make_frame(image)
        proc = CombatLogPreprocessor()

        result = proc.process(frame)

        assert result.shape[0] == 100  # height * 2
        assert result.shape[1] == 200  # width * 2

    def test_process_returns_binary(self) -> None:
        """process()는 0 또는 255 값만 포함하는 이진 이미지를 반환한다."""
        image = np.random.randint(0, 256, (30, 60, 3), dtype=np.uint8)
        frame = _make_frame(image)
        proc = CombatLogPreprocessor()

        result = proc.process(frame)

        unique_values = set(np.unique(result))
        assert unique_values <= {0, 255}

    def test_process_with_matching_color(self) -> None:
        """색상 범위에 해당하는 픽셀은 흰색(255)이 된다."""
        # 색상 범위: BGR (100, 100, 100) ~ (200, 200, 200)
        cr = ColorRange("test", (100, 100, 100), (200, 200, 200))
        proc = CombatLogPreprocessor(color_ranges=[cr])

        # 범위 내 픽셀
        image = np.full((10, 20, 3), 150, dtype=np.uint8)
        frame = _make_frame(image)
        result = proc.process(frame)

        assert np.all(result == 255)

    def test_process_with_no_matching_color(self) -> None:
        """색상 범위에 해당하지 않는 픽셀은 검은색(0)이 된다."""
        cr = ColorRange("test", (100, 100, 100), (200, 200, 200))
        proc = CombatLogPreprocessor(color_ranges=[cr])

        # 범위 밖 픽셀
        image = np.full((10, 20, 3), 50, dtype=np.uint8)
        frame = _make_frame(image)
        result = proc.process(frame)

        assert np.all(result == 0)

    def test_is_duplicate_same_image(self) -> None:
        """동일한 이미지는 True를 반환한다."""
        image = np.ones((10, 20, 3), dtype=np.uint8) * 128
        frame = _make_frame(image)
        proc = CombatLogPreprocessor()

        # 첫 번째 호출은 항상 False (이전 해시 없음)
        assert proc.is_duplicate(frame) is False
        # 동일 이미지 두 번째 호출
        assert proc.is_duplicate(frame) is True

    def test_is_duplicate_different_image(self) -> None:
        """다른 이미지는 False를 반환한다."""
        image1 = np.zeros((10, 20, 3), dtype=np.uint8)
        image2 = np.ones((10, 20, 3), dtype=np.uint8) * 255
        frame1 = _make_frame(image1)
        frame2 = _make_frame(image2)
        proc = CombatLogPreprocessor()

        assert proc.is_duplicate(frame1) is False
        assert proc.is_duplicate(frame2) is False
