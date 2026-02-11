# Phase 7a: OCR 핵심 엔진 개선 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** OCR 인식률을 향상시키기 위해 전처리 파이프라인 고도화, EasyOCR 엔진 추가, 파서 강화, OCR 디버그 도구를 구현한다.

**Architecture:** 기존 `CombatLogPreprocessor`를 다단계 파이프라인으로 확장하고, `EasyOcrEngine`을 새로 추가하며, `OcrEngineManager`에 confidence 기반 선택 모드를 도입한다. `KoreanCombatParser`에 miss/resist 패턴과 fuzzy fallback을 추가한다. `OcrDebugger`로 프레임별 결과를 덤프하여 디버깅을 지원한다.

**Tech Stack:** Python 3.12+, OpenCV, NumPy, EasyOCR (optional), pytest

---

## Task 1: 전처리 파이프라인 모델 확장

**Files:**
- Modify: `src/aion2meter/models.py:93-126`
- Test: `tests/test_config.py`

### Step 1: Write the failing test

`tests/test_config.py` 파일 끝에 추가:

```python
class TestPreprocessConfig:
    """전처리 설정 테스트."""

    def test_default_preprocess_config(self):
        from aion2meter.models import PreprocessConfig
        config = AppConfig()
        assert config.preprocess is not None
        assert config.preprocess.upscale_factor == 2
        assert config.preprocess.denoise is True
        assert config.preprocess.sharpen is True
        assert config.preprocess.adaptive_threshold is False
        assert config.preprocess.cleanup_min_area == 10

    def test_preprocess_config_roundtrip(self, tmp_path):
        from aion2meter.models import PreprocessConfig
        config = AppConfig(
            preprocess=PreprocessConfig(
                upscale_factor=3,
                denoise=False,
                sharpen=True,
                adaptive_threshold=True,
                cleanup_min_area=20,
            ),
        )
        mgr = ConfigManager(default_path=tmp_path / "config.toml")
        mgr.save(config)
        loaded = mgr.load()
        assert loaded.preprocess.upscale_factor == 3
        assert loaded.preprocess.denoise is False
        assert loaded.preprocess.sharpen is True
        assert loaded.preprocess.adaptive_threshold is True
        assert loaded.preprocess.cleanup_min_area == 20
```

### Step 2: Run test to verify it fails

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_config.py::TestPreprocessConfig -v`
Expected: FAIL — `PreprocessConfig` not defined

### Step 3: Write minimal implementation

**`src/aion2meter/models.py`** — `AppConfig` 위에 추가:

```python
@dataclass(frozen=True)
class PreprocessConfig:
    """전처리 파이프라인 설정."""

    upscale_factor: int = 2
    denoise: bool = True
    sharpen: bool = True
    adaptive_threshold: bool = False
    cleanup_min_area: int = 10
```

**`src/aion2meter/models.py`** — `AppConfig`에 필드 추가:

```python
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
```

주의: `AppConfig`는 `frozen=True`가 아니므로 `field(default_factory=...)` 사용 가능.

**`src/aion2meter/config.py`** — `load()` 메서드에서 `preprocess` 읽기 추가:

```python
from aion2meter.models import AppConfig, ColorRange, PreprocessConfig, ROI
```

`load()` 함수에서 `return AppConfig(...)` 호출 전에:

```python
        # preprocess 설정
        preprocess_data = data.get("preprocess", {})
        preprocess = PreprocessConfig(
            upscale_factor=int(preprocess_data.get("upscale_factor", 2)),
            denoise=bool(preprocess_data.get("denoise", True)),
            sharpen=bool(preprocess_data.get("sharpen", True)),
            adaptive_threshold=bool(preprocess_data.get("adaptive_threshold", False)),
            cleanup_min_area=int(preprocess_data.get("cleanup_min_area", 10)),
        )
```

`return AppConfig(...)`에 `preprocess=preprocess,` 추가.

**`src/aion2meter/config.py`** — `_serialize()` 메서드에서 `preprocess` 직렬화 추가:

ROI 섹션 전에:

```python
        # preprocess
        lines.append("")
        lines.append("[preprocess]")
        lines.append(f"upscale_factor = {config.preprocess.upscale_factor}")
        lines.append(f"denoise = {'true' if config.preprocess.denoise else 'false'}")
        lines.append(f"sharpen = {'true' if config.preprocess.sharpen else 'false'}")
        lines.append(f"adaptive_threshold = {'true' if config.preprocess.adaptive_threshold else 'false'}")
        lines.append(f"cleanup_min_area = {config.preprocess.cleanup_min_area}")
```

### Step 4: Run test to verify it passes

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_config.py -v`
Expected: ALL PASS (기존 14개 + 새 2개 = 16개)

### Step 5: Commit

```bash
git add src/aion2meter/models.py src/aion2meter/config.py tests/test_config.py
git commit -m "feat(P1): add PreprocessConfig model and TOML serialization"
```

---

## Task 2: 전처리 파이프라인 구현

**Files:**
- Modify: `src/aion2meter/preprocess/image_proc.py`
- Test: `tests/test_preprocess.py`

### Step 1: Write the failing tests

`tests/test_preprocess.py` 파일 끝에 추가:

```python
class TestPreprocessPipeline:
    """전처리 파이프라인 스텝 테스트."""

    def test_denoise_removes_salt_pepper_noise(self) -> None:
        """denoise 스텝이 salt-and-pepper 노이즈를 줄인다."""
        from aion2meter.models import PreprocessConfig
        # 흰색 텍스트 + salt-pepper 노이즈 이미지 생성
        cr = ColorRange("white", (200, 200, 200), (255, 255, 255))
        image = np.full((20, 40, 3), 220, dtype=np.uint8)
        # 노이즈 추가: 랜덤 픽셀을 0 또는 255로
        rng = np.random.RandomState(42)
        noise_mask = rng.random(image.shape[:2]) < 0.05
        image[noise_mask] = 0
        frame = _make_frame(image)

        proc_no_denoise = CombatLogPreprocessor(
            color_ranges=[cr],
            preprocess_config=PreprocessConfig(denoise=False, sharpen=False),
        )
        proc_denoise = CombatLogPreprocessor(
            color_ranges=[cr],
            preprocess_config=PreprocessConfig(denoise=True, sharpen=False),
        )

        result_noisy = proc_no_denoise.process(frame)
        result_clean = proc_denoise.process(frame)

        # denoise 적용 시 흰색 픽셀이 더 많아야 함 (노이즈 제거)
        white_noisy = np.count_nonzero(result_noisy == 255)
        white_clean = np.count_nonzero(result_clean == 255)
        assert white_clean >= white_noisy

    def test_sharpen_preserves_shape(self) -> None:
        """sharpen 스텝이 출력 크기를 변경하지 않는다."""
        from aion2meter.models import PreprocessConfig
        cr = ColorRange("test", (100, 100, 100), (200, 200, 200))
        image = np.full((20, 40, 3), 150, dtype=np.uint8)
        frame = _make_frame(image)
        proc = CombatLogPreprocessor(
            color_ranges=[cr],
            preprocess_config=PreprocessConfig(sharpen=True, denoise=False),
        )
        result = proc.process(frame)
        assert result.shape == (40, 80)  # 2x upscale

    def test_cleanup_removes_small_blobs(self) -> None:
        """cleanup 스텝이 작은 blob을 제거한다."""
        from aion2meter.models import PreprocessConfig
        cr = ColorRange("white", (200, 200, 200), (255, 255, 255))
        # 대부분 검은 배경 + 작은 흰 점 (노이즈)
        image = np.zeros((30, 60, 3), dtype=np.uint8)
        # 3x3 작은 흰 영역 (area=9, cleanup_min_area=50이면 제거됨)
        image[5:8, 5:8] = 220
        # 큰 흰 영역 (area=100, 유지됨)
        image[15:25, 20:30] = 220
        frame = _make_frame(image)

        proc = CombatLogPreprocessor(
            color_ranges=[cr],
            preprocess_config=PreprocessConfig(
                denoise=False, sharpen=False, cleanup_min_area=50,
            ),
        )
        result = proc.process(frame)
        # 작은 blob은 제거, 큰 blob은 유지
        assert np.count_nonzero(result) > 0  # 큰 blob 유지

    def test_upscale_factor_configurable(self) -> None:
        """upscale_factor가 설정대로 적용된다."""
        from aion2meter.models import PreprocessConfig
        cr = ColorRange("test", (100, 100, 100), (200, 200, 200))
        image = np.full((20, 40, 3), 150, dtype=np.uint8)
        frame = _make_frame(image)
        proc = CombatLogPreprocessor(
            color_ranges=[cr],
            preprocess_config=PreprocessConfig(upscale_factor=3, denoise=False, sharpen=False),
        )
        result = proc.process(frame)
        assert result.shape == (60, 120)  # 3x upscale

    def test_default_preprocess_config_backward_compatible(self) -> None:
        """PreprocessConfig 없이 생성해도 기존 동작과 동일하다."""
        cr = ColorRange("test", (100, 100, 100), (200, 200, 200))
        image = np.full((10, 20, 3), 150, dtype=np.uint8)
        frame = _make_frame(image)

        proc_old = CombatLogPreprocessor(color_ranges=[cr])
        result = proc_old.process(frame)
        # 기존 테스트와 동일: 2x, binary
        assert result.shape == (20, 40)
        assert np.all(result == 255)
```

### Step 2: Run test to verify it fails

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_preprocess.py::TestPreprocessPipeline -v`
Expected: FAIL — `CombatLogPreprocessor` doesn't accept `preprocess_config`

### Step 3: Write minimal implementation

**`src/aion2meter/preprocess/image_proc.py`** 전체를 다음으로 교체:

```python
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
```

### Step 4: Run test to verify it passes

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_preprocess.py -v`
Expected: ALL PASS (기존 6개 + 새 5개 = 11개)

### Step 5: Commit

```bash
git add src/aion2meter/preprocess/image_proc.py tests/test_preprocess.py
git commit -m "feat(P1): add denoise, sharpen, cleanup preprocessing steps"
```

---

## Task 3: EasyOCR 엔진 추가

**Files:**
- Create: `src/aion2meter/ocr/easyocr_engine.py`
- Test: `tests/test_easyocr_engine.py`

### Step 1: Write the failing test

Create `tests/test_easyocr_engine.py`:

```python
"""EasyOCR 엔진 단위 테스트."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from aion2meter.models import OcrResult


class TestEasyOcrEngine:
    """EasyOcrEngine 테스트."""

    def test_implements_ocr_engine_protocol(self) -> None:
        """OcrEngine Protocol을 구현한다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        from aion2meter.protocols import OcrEngine
        engine = EasyOcrEngine(gpu=False)
        assert isinstance(engine, OcrEngine)

    def test_recognize_returns_ocr_result(self) -> None:
        """recognize()는 OcrResult를 반환한다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        engine = EasyOcrEngine(gpu=False)

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = [
            ([[0, 0], [100, 0], [100, 30], [0, 30]], "몬스터에게 검격을 사용해 1,234의 대미지를 줬습니다", 0.95),
        ]
        engine._reader = mock_reader

        image = np.zeros((30, 100), dtype=np.uint8)
        result = engine.recognize(image)

        assert isinstance(result, OcrResult)
        assert "몬스터" in result.text
        assert result.confidence == pytest.approx(0.95)
        mock_reader.readtext.assert_called_once()

    def test_recognize_joins_multiple_lines(self) -> None:
        """여러 라인의 OCR 결과를 줄바꿈으로 결합한다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        engine = EasyOcrEngine(gpu=False)

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = [
            ([[0, 0], [100, 0], [100, 15], [0, 15]], "라인1", 0.90),
            ([[0, 15], [100, 15], [100, 30], [0, 30]], "라인2", 0.80),
        ]
        engine._reader = mock_reader

        image = np.zeros((30, 100), dtype=np.uint8)
        result = engine.recognize(image)

        assert result.text == "라인1\n라인2"
        assert result.confidence == pytest.approx(0.85)  # (0.90 + 0.80) / 2

    def test_recognize_empty_result(self) -> None:
        """OCR 결과가 없으면 빈 텍스트와 confidence 0을 반환한다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        engine = EasyOcrEngine(gpu=False)

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = []
        engine._reader = mock_reader

        image = np.zeros((30, 100), dtype=np.uint8)
        result = engine.recognize(image)

        assert result.text == ""
        assert result.confidence == 0.0

    def test_lazy_init_not_called_until_recognize(self) -> None:
        """EasyOCR reader는 recognize() 호출 전까지 초기화되지 않는다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        engine = EasyOcrEngine(gpu=False)
        assert engine._reader is None

    def test_import_error_raises_runtime_error(self) -> None:
        """easyocr가 설치되지 않으면 RuntimeError가 발생한다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        engine = EasyOcrEngine(gpu=False)

        with patch.dict("sys.modules", {"easyocr": None}):
            with pytest.raises(RuntimeError, match="easyocr"):
                engine._ensure_reader()
```

### Step 2: Run test to verify it fails

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_easyocr_engine.py -v`
Expected: FAIL — `easyocr_engine` module not found

### Step 3: Write minimal implementation

Create `src/aion2meter/ocr/easyocr_engine.py`:

```python
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
```

### Step 4: Run test to verify it passes

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_easyocr_engine.py -v`
Expected: ALL PASS (6개)

### Step 5: Commit

```bash
git add src/aion2meter/ocr/easyocr_engine.py tests/test_easyocr_engine.py
git commit -m "feat(P2): add EasyOCR engine with lazy init and Protocol compliance"
```

---

## Task 4: OcrEngineManager best_confidence 모드

**Files:**
- Modify: `src/aion2meter/ocr/engine_manager.py`
- Modify: `src/aion2meter/models.py`
- Test: `tests/test_ocr.py`

### Step 1: Write the failing tests

`tests/test_ocr.py` 파일 끝에 추가:

```python
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
```

### Step 2: Run test to verify it fails

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_ocr.py::TestBestConfidenceMode -v`
Expected: FAIL — `OcrEngineManager` doesn't accept `mode`

### Step 3: Write minimal implementation

**`src/aion2meter/ocr/engine_manager.py`** — `__init__`에 `mode` 파라미터 추가, `recognize`에 best_confidence 로직 추가:

```python
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

    mode:
        - "failover" (기본): primary 실패 시 fallback 전환
        - "best_confidence": 두 엔진 결과 중 confidence 높은 쪽 채택
    """

    def __init__(
        self,
        primary: OcrEngine,
        fallback: OcrEngine | None = None,
        max_failures: int = 3,
        mode: str = "failover",
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._max_failures = max_failures
        self._failure_count: int = 0
        self._using_fallback: bool = False
        self._mode = mode

    def recognize(self, image: np.ndarray) -> OcrResult:
        """이미지에서 텍스트를 인식한다."""
        if self._mode == "best_confidence":
            return self._recognize_best_confidence(image)
        return self._recognize_failover(image)

    def _recognize_best_confidence(self, image: np.ndarray) -> OcrResult:
        """두 엔진 결과 중 confidence가 높은 쪽을 반환한다."""
        primary_result: OcrResult | None = None
        fallback_result: OcrResult | None = None

        try:
            primary_result = self._primary.recognize(image)
        except Exception:
            logger.warning("best_confidence: primary OCR 실패")

        if self._fallback is not None:
            try:
                fallback_result = self._fallback.recognize(image)
            except Exception:
                logger.warning("best_confidence: fallback OCR 실패")

        if primary_result and fallback_result:
            return primary_result if primary_result.confidence >= fallback_result.confidence else fallback_result
        if primary_result:
            return primary_result
        if fallback_result:
            return fallback_result
        return self._empty_result()

    def _recognize_failover(self, image: np.ndarray) -> OcrResult:
        """기존 failover 로직."""
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
```

### Step 4: Run test to verify it passes

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_ocr.py -v`
Expected: ALL PASS (기존 6개 + 새 4개 = 10개)

### Step 5: Commit

```bash
git add src/aion2meter/ocr/engine_manager.py tests/test_ocr.py
git commit -m "feat(P2): add best_confidence mode to OcrEngineManager"
```

---

## Task 5: AppConfig OCR 필드 확장

**Files:**
- Modify: `src/aion2meter/models.py`
- Modify: `src/aion2meter/config.py`
- Test: `tests/test_config.py`

### Step 1: Write the failing test

`tests/test_config.py` 파일 끝에 추가:

```python
class TestOcrEngineConfig:
    """OCR 엔진 설정 직렬화/역직렬화."""

    def test_default_ocr_config(self):
        config = AppConfig()
        assert config.ocr_engine == "winocr"
        assert config.ocr_fallback == ""
        assert config.ocr_mode == "failover"
        assert config.ocr_debug is False

    def test_ocr_config_roundtrip(self, tmp_path):
        config = AppConfig(
            ocr_engine="easyocr",
            ocr_fallback="tesseract",
            ocr_mode="best_confidence",
            ocr_debug=True,
        )
        mgr = ConfigManager(default_path=tmp_path / "config.toml")
        mgr.save(config)
        loaded = mgr.load()
        assert loaded.ocr_engine == "easyocr"
        assert loaded.ocr_fallback == "tesseract"
        assert loaded.ocr_mode == "best_confidence"
        assert loaded.ocr_debug is True
```

### Step 2: Run test to verify it fails

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_config.py::TestOcrEngineConfig -v`
Expected: FAIL — `AppConfig` has no `ocr_fallback`

### Step 3: Write minimal implementation

**`src/aion2meter/models.py`** — `AppConfig`에 필드 추가 (`ocr_engine` 바로 아래에):

```python
    ocr_fallback: str = ""
    ocr_mode: str = "failover"
    ocr_debug: bool = False
```

**`src/aion2meter/config.py`** — `load()` 메서드에서 새 필드 읽기:

`return AppConfig(...)` 호출에 추가:
```python
            ocr_fallback=str(data.get("ocr_fallback", "")),
            ocr_mode=str(data.get("ocr_mode", "failover")),
            ocr_debug=bool(data.get("ocr_debug", False)),
```

**`src/aion2meter/config.py`** — `_serialize()` 메서드에서 새 필드 직렬화:

`ocr_engine` 줄 다음에:
```python
        lines.append(f'ocr_fallback = "{_esc(config.ocr_fallback)}"')
        lines.append(f'ocr_mode = "{_esc(config.ocr_mode)}"')
        lines.append(f"ocr_debug = {'true' if config.ocr_debug else 'false'}")
```

### Step 4: Run test to verify it passes

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_config.py -v`
Expected: ALL PASS (기존 + 새 2개)

### Step 5: Commit

```bash
git add src/aion2meter/models.py src/aion2meter/config.py tests/test_config.py
git commit -m "feat(P2): add ocr_fallback, ocr_mode, ocr_debug to AppConfig"
```

---

## Task 6: 파서 강화 — HitType 확장 + OCR 보정

**Files:**
- Modify: `src/aion2meter/models.py`
- Modify: `src/aion2meter/parser/combat_parser.py`
- Test: `tests/test_parser.py`

### Step 1: Write the failing tests

`tests/test_parser.py` 파일 끝에 추가:

```python
class TestMissResist:
    """빗나감/저항 파싱."""

    def test_miss_pattern(self, parser: KoreanCombatParser):
        text = "몬스터에게 검격을 사용했지만 빗나갔습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        evt = events[0]
        assert evt.target == "몬스터"
        assert evt.skill == "검격"
        assert evt.damage == 0
        assert evt.hit_type == HitType.MISS

    def test_resist_pattern(self, parser: KoreanCombatParser):
        text = "몬스터에게 화염구를 사용했지만 저항했습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        evt = events[0]
        assert evt.target == "몬스터"
        assert evt.skill == "화염구"
        assert evt.damage == 0
        assert evt.hit_type == HitType.RESIST


class TestExtendedOcrCorrection:
    """확장된 OCR 보정 테스트."""

    def test_사용혜_correction(self, parser: KoreanCombatParser):
        text = "몬스터에게 검격을 사용혜 1,234의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        assert events[0].damage == 1234

    def test_줬숨니다_correction(self, parser: KoreanCombatParser):
        text = "몬스터에게 검격을 사용해 1,234의 대미지를 줬숨니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        assert events[0].damage == 1234

    def test_digit_D_to_0(self, parser: KoreanCombatParser):
        text = "몬스터에게 검격을 사용해 1,D34의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        assert events[0].damage == 1034


class TestFuzzyFallback:
    """Fuzzy fallback 파싱 테스트."""

    def test_fuzzy_extracts_damage_from_garbled_text(self, parser: KoreanCombatParser):
        """정규식 매칭 실패해도 핵심 키워드가 있으면 대미지를 추출한다."""
        # '사용해' 대신 '사용하여' (정규식에 없는 패턴)
        text = "몬스터에게 검격 사용하여 5,678의 대미지를 줬습니다"
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        assert events[0].damage == 5678

    def test_fuzzy_no_damage_number_returns_empty(self, parser: KoreanCombatParser):
        """대미지 숫자가 없으면 fuzzy도 이벤트를 생성하지 않는다."""
        text = "몬스터에게 대미지를 줬습니다"
        events = parser.parse(text, 1.0)
        assert events == []
```

### Step 2: Run test to verify it fails

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_parser.py::TestMissResist tests/test_parser.py::TestExtendedOcrCorrection tests/test_parser.py::TestFuzzyFallback -v`
Expected: FAIL — `HitType.MISS` not defined

### Step 3: Write minimal implementation

**`src/aion2meter/models.py`** — `HitType`에 추가:

```python
    MISS = "빗나감"
    RESIST = "저항"
```

**`src/aion2meter/parser/combat_parser.py`** — 보정 딕셔너리 확장:

```python
_OCR_TEXT_CORRECTIONS: dict[str, str] = {
    "대머지": "대미지",
    "대미저": "대미지",
    "대머저": "대미지",
    "사용혜": "사용해",
    "사웅해": "사용해",
    "줬숨니다": "줬습니다",
    "줬습나다": "줬습니다",
    "줬숩니다": "줬습니다",
    "빗나갔숨니다": "빗나갔습니다",
    "저항했숨니다": "저항했습니다",
}

_OCR_DIGIT_MAP: dict[str, str] = {
    "O": "0",
    "o": "0",
    "l": "1",
    "I": "1",
    "B": "8",
    "S": "5",
    "Z": "2",
    "G": "6",
    "D": "0",
    "Q": "0",
    "U": "0",
}
```

`_NUM` 패턴 업데이트 (D, Q, U 추가):

```python
_NUM = r"[\d,.\-OolIBSZGDQU]"
_NUM_START = r"[\dOolIBSZGDQU]"
```

miss/resist 정규식 추가 (파일 상단, `_RE_ADDITIONAL` 뒤에):

```python
# 정규식: 빗나감
_RE_MISS = re.compile(
    r"(.*?)에게\s+(.*?)[을를]\s*사용했지만\s*빗나갔습니다"
)

# 정규식: 저항
_RE_RESIST = re.compile(
    r"(.*?)에게\s+(.*?)[을를]\s*사용했지만\s*저항했습니다"
)

# Fuzzy fallback: "에게" + 숫자 + "대미지"
_RE_FUZZY_DAMAGE = re.compile(
    rf"(.*?)에게\s+.*?({_NUM_START}{_NUM}*)\s*의\s*대미지"
)
```

**`src/aion2meter/parser/combat_parser.py`** — `_parse_line()` 메서드 확장:

추가 대미지 체크 후, modifier/normal 체크 전에 miss/resist 추가:

```python
    def _parse_line(self, line: str, timestamp: float) -> DamageEvent | None:
        """한 줄을 파싱하여 DamageEvent를 반환. 매칭 실패 시 None."""
        # 1) 추가 대미지 먼저 체크 (더 구체적)
        m = _RE_ADDITIONAL.search(line)
        if m:
            target = m.group(1).strip()
            damage = _parse_number(m.group(2))
            return DamageEvent(
                timestamp=timestamp,
                source="",
                target=target,
                skill="",
                damage=damage,
                hit_type=HitType.NORMAL,
                is_additional=True,
            )

        # 1.5) 빗나감/저항 (대미지 0)
        m = _RE_MISS.search(line)
        if m:
            return DamageEvent(
                timestamp=timestamp,
                source="",
                target=m.group(1).strip(),
                skill=m.group(2).strip(),
                damage=0,
                hit_type=HitType.MISS,
            )

        m = _RE_RESIST.search(line)
        if m:
            return DamageEvent(
                timestamp=timestamp,
                source="",
                target=m.group(1).strip(),
                skill=m.group(2).strip(),
                damage=0,
                hit_type=HitType.RESIST,
            )

        # 2) 배율 포함 대미지
        m = _RE_MODIFIER.search(line)
        if m:
            target = m.group(1).strip()
            modifier_raw = m.group(2).strip()
            modifier_key = re.sub(r"\s+", " ", modifier_raw)
            skill = m.group(3).strip()
            damage = _parse_number(m.group(4))
            hit_type = _HIT_TYPE_MAP.get(modifier_key, HitType.NORMAL)
            return DamageEvent(
                timestamp=timestamp,
                source="",
                target=target,
                skill=skill,
                damage=damage,
                hit_type=hit_type,
                is_additional=False,
            )

        # 3) 일반 대미지
        m = _RE_NORMAL.search(line)
        if m:
            target = m.group(1).strip()
            skill = m.group(2).strip()
            damage = _parse_number(m.group(3))
            return DamageEvent(
                timestamp=timestamp,
                source="",
                target=target,
                skill=skill,
                damage=damage,
                hit_type=HitType.NORMAL,
                is_additional=False,
            )

        # 4) Fuzzy fallback: "에게" + 숫자 + "대미지" 키워드만으로 추출
        m = _RE_FUZZY_DAMAGE.search(line)
        if m:
            target = m.group(1).strip()
            try:
                damage = _parse_number(m.group(2))
            except (ValueError, IndexError):
                return None
            if damage <= 0:
                return None
            return DamageEvent(
                timestamp=timestamp,
                source="",
                target=target,
                skill="",
                damage=damage,
                hit_type=HitType.NORMAL,
                is_additional=False,
            )

        return None
```

### Step 4: Run test to verify it passes

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_parser.py -v`
Expected: ALL PASS (기존 테스트 + 새 7개)

### Step 5: Commit

```bash
git add src/aion2meter/models.py src/aion2meter/parser/combat_parser.py tests/test_parser.py
git commit -m "feat(P3): add miss/resist patterns, extended OCR corrections, fuzzy fallback"
```

---

## Task 7: OCR 디버그 도구

**Files:**
- Create: `src/aion2meter/io/ocr_debugger.py`
- Test: `tests/test_ocr_debugger.py`

### Step 1: Write the failing test

Create `tests/test_ocr_debugger.py`:

```python
"""OCR 디버그 도구 단위 테스트."""

from __future__ import annotations

import json

import numpy as np
import pytest

from aion2meter.models import DamageEvent, HitType


class TestOcrDebugger:
    """OcrDebugger 테스트."""

    def test_dump_creates_files(self, tmp_path) -> None:
        """enabled=True이면 프레임 디렉토리와 파일들을 생성한다."""
        from aion2meter.io.ocr_debugger import OcrDebugger

        debugger = OcrDebugger(output_dir=tmp_path / "debug", enabled=True)
        raw = np.zeros((10, 20, 3), dtype=np.uint8)
        processed = np.zeros((20, 40), dtype=np.uint8)
        ocr_text = "테스트 텍스트"
        events = [
            DamageEvent(timestamp=1.0, source="", target="몬스터", skill="검격", damage=100, hit_type=HitType.NORMAL),
        ]

        debugger.dump(raw, processed, ocr_text, events)

        frame_dir = tmp_path / "debug" / "frame_000001"
        assert frame_dir.exists()
        assert (frame_dir / "raw.png").exists()
        assert (frame_dir / "processed.png").exists()
        assert (frame_dir / "ocr.txt").read_text(encoding="utf-8") == "테스트 텍스트"
        events_data = json.loads((frame_dir / "events.json").read_text(encoding="utf-8"))
        assert len(events_data) == 1
        assert events_data[0]["damage"] == 100

    def test_dump_disabled_creates_nothing(self, tmp_path) -> None:
        """enabled=False이면 아무 파일도 생성하지 않는다."""
        from aion2meter.io.ocr_debugger import OcrDebugger

        debugger = OcrDebugger(output_dir=tmp_path / "debug", enabled=False)
        raw = np.zeros((10, 20, 3), dtype=np.uint8)
        processed = np.zeros((20, 40), dtype=np.uint8)

        debugger.dump(raw, processed, "text", [])

        assert not (tmp_path / "debug").exists()

    def test_dump_increments_counter(self, tmp_path) -> None:
        """dump()를 여러 번 호출하면 카운터가 증가한다."""
        from aion2meter.io.ocr_debugger import OcrDebugger

        debugger = OcrDebugger(output_dir=tmp_path / "debug", enabled=True)
        raw = np.zeros((10, 20, 3), dtype=np.uint8)
        processed = np.zeros((20, 40), dtype=np.uint8)

        debugger.dump(raw, processed, "1", [])
        debugger.dump(raw, processed, "2", [])

        assert (tmp_path / "debug" / "frame_000001").exists()
        assert (tmp_path / "debug" / "frame_000002").exists()

    def test_dump_with_empty_events(self, tmp_path) -> None:
        """이벤트가 비어있어도 정상 동작한다."""
        from aion2meter.io.ocr_debugger import OcrDebugger

        debugger = OcrDebugger(output_dir=tmp_path / "debug", enabled=True)
        raw = np.zeros((10, 20, 3), dtype=np.uint8)
        processed = np.zeros((20, 40), dtype=np.uint8)

        debugger.dump(raw, processed, "", [])

        frame_dir = tmp_path / "debug" / "frame_000001"
        events_data = json.loads((frame_dir / "events.json").read_text(encoding="utf-8"))
        assert events_data == []
```

### Step 2: Run test to verify it fails

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_ocr_debugger.py -v`
Expected: FAIL — `ocr_debugger` module not found

### Step 3: Write minimal implementation

Create `src/aion2meter/io/ocr_debugger.py`:

```python
"""OCR 디버그 프레임 덤프."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from aion2meter.models import DamageEvent


class OcrDebugger:
    """OCR 파이프라인 결과를 프레임별로 파일에 덤프한다."""

    def __init__(self, output_dir: Path, enabled: bool = False) -> None:
        self._output_dir = output_dir
        self._enabled = enabled
        self._counter = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def dump(
        self,
        raw_frame: np.ndarray,
        processed_image: np.ndarray,
        ocr_text: str,
        parsed_events: list[DamageEvent],
    ) -> None:
        """한 프레임의 전체 파이프라인 결과를 저장한다."""
        if not self._enabled:
            return

        self._counter += 1
        frame_dir = self._output_dir / f"frame_{self._counter:06d}"
        frame_dir.mkdir(parents=True, exist_ok=True)

        cv2.imwrite(str(frame_dir / "raw.png"), raw_frame)
        cv2.imwrite(str(frame_dir / "processed.png"), processed_image)
        (frame_dir / "ocr.txt").write_text(ocr_text, encoding="utf-8")

        events_data = []
        for e in parsed_events:
            d = asdict(e)
            d["hit_type"] = e.hit_type.value
            events_data.append(d)

        (frame_dir / "events.json").write_text(
            json.dumps(events_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

### Step 4: Run test to verify it passes

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest tests/test_ocr_debugger.py -v`
Expected: ALL PASS (4개)

### Step 5: Commit

```bash
git add src/aion2meter/io/ocr_debugger.py tests/test_ocr_debugger.py
git commit -m "feat(P4): add OcrDebugger for pipeline frame dumping"
```

---

## Task 8: 통합 — 파이프라인에 전처리 설정 + EasyOCR + 디버거 연결

**Files:**
- Modify: `src/aion2meter/pipeline/pipeline.py`
- Modify: `src/aion2meter/pyproject.toml`
- Modify: `src/aion2meter/config.py` (설정 UI 필드만)

### Step 1: Modify pipeline to use PreprocessConfig

**`src/aion2meter/pipeline/pipeline.py`** — `DpsPipeline.__init__`에서 `CombatLogPreprocessor`에 `preprocess_config` 전달:

```python
from aion2meter.models import AppConfig, CapturedFrame, DpsSnapshot, PreprocessConfig, ROI
```

`__init__` 내에서:
```python
        self._preprocessor = CombatLogPreprocessor(
            config.color_ranges or AppConfig.default_color_ranges(),
            preprocess_config=config.preprocess,
        )
```

### Step 2: Add EasyOCR to build options

**`src/aion2meter/pipeline/pipeline.py`** — `_build_default_ocr`에 easyocr 옵션 추가:

```python
    def _build_default_ocr(self) -> object:
        """기본 OCR 엔진 생성. 설정에 따라 선택."""
        engine_name = self._config.ocr_engine

        if engine_name == "easyocr":
            try:
                from aion2meter.ocr.easyocr_engine import EasyOcrEngine
                return EasyOcrEngine(gpu=True)
            except Exception:
                pass

        if engine_name == "winocr" or engine_name == "easyocr":
            try:
                from aion2meter.ocr.winocr_engine import WinOcrEngine
                return WinOcrEngine()
            except Exception:
                pass

        try:
            from aion2meter.ocr.tesseract_engine import TesseractEngine
            return TesseractEngine()
        except Exception:
            pass

        raise RuntimeError("사용 가능한 OCR 엔진이 없습니다.")
```

`__init__`에서 fallback 엔진도 빌드:

```python
        primary_ocr = ocr_engine or self._build_default_ocr()
        fallback_ocr = self._build_fallback_ocr() if config.ocr_fallback else None
        self._ocr_engine = (
            ocr_engine
            if isinstance(ocr_engine, OcrEngineManager)
            else OcrEngineManager(
                primary=primary_ocr,
                fallback=fallback_ocr,
                mode=config.ocr_mode,
            )
        )
```

새 메서드:

```python
    def _build_fallback_ocr(self) -> object | None:
        """fallback OCR 엔진을 생성한다."""
        name = self._config.ocr_fallback
        try:
            if name == "easyocr":
                from aion2meter.ocr.easyocr_engine import EasyOcrEngine
                return EasyOcrEngine(gpu=True)
            elif name == "winocr":
                from aion2meter.ocr.winocr_engine import WinOcrEngine
                return WinOcrEngine()
            elif name == "tesseract":
                from aion2meter.ocr.tesseract_engine import TesseractEngine
                return TesseractEngine()
        except Exception:
            pass
        return None
```

### Step 3: Add OcrDebugger to OcrWorker

**`src/aion2meter/pipeline/pipeline.py`** — `OcrWorker`에 debugger 파라미터 추가:

```python
from aion2meter.io.ocr_debugger import OcrDebugger
```

`OcrWorker.__init__`에:
```python
        self._debugger: OcrDebugger | None = None
```

`OcrWorker`에 setter:
```python
    def set_debugger(self, debugger: OcrDebugger) -> None:
        self._debugger = debugger
```

`OcrWorker.run()` 내에서 OCR 처리 후:

```python
            processed = self._preprocessor.process(frame)
            ocr_result = self._ocr_engine.recognize(processed)

            if not ocr_result.text.strip():
                if self._debugger:
                    self._debugger.dump(frame.image, processed, "", [])
                continue

            events = self._parser.parse(ocr_result.text, frame.timestamp)

            if self._debugger:
                self._debugger.dump(frame.image, processed, ocr_result.text, events)

            if events:
                snapshot = self._calculator.add_events(events)
                self.dps_updated.emit(snapshot)
```

`DpsPipeline.start()`에서 debugger 설정:

```python
        if self._config.ocr_debug:
            from pathlib import Path
            debug_dir = Path.home() / ".aion2meter" / "debug"
            debugger = OcrDebugger(output_dir=debug_dir, enabled=True)
            self._ocr_worker.set_debugger(debugger)
```

### Step 4: Update pyproject.toml

**`pyproject.toml`** — optional dependencies에 easyocr 추가:

```toml
[project.optional-dependencies]
winocr = ["winocr>=0.2"]
tesseract = ["pytesseract>=0.3"]
easyocr = ["easyocr>=1.7"]
dev = [
    "pytest>=8.0",
    "pytest-qt>=4.3",
]
build = ["pyinstaller>=6.0"]
```

### Step 5: Run all tests

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest -v`
Expected: ALL PASS (기존 168개 + 새 테스트)

### Step 6: Commit

```bash
git add src/aion2meter/pipeline/pipeline.py pyproject.toml
git commit -m "feat(P5): integrate preprocessing config, EasyOCR, and debugger into pipeline"
```

---

## Task 9: 전체 테스트 + 정리

### Step 1: 전체 테스트 실행

Run: `cd /home/kdw73/projects/아이온2서드파티 && .venv/bin/pytest -v --tb=short`
Expected: ALL PASS

### Step 2: import 검증

Run: `cd /home/kdw73/projects/아이온2서드파티 && PYTHONPATH=src .venv/bin/python -c "from aion2meter.preprocess.image_proc import CombatLogPreprocessor; from aion2meter.ocr.easyocr_engine import EasyOcrEngine; from aion2meter.io.ocr_debugger import OcrDebugger; from aion2meter.models import PreprocessConfig, HitType; print('HitType values:', [h.value for h in HitType]); print('OK')"`
Expected: OK 출력, HitType에 "빗나감", "저항" 포함

### Step 3: Final commit

```bash
git add -A
git commit -m "feat: Phase 7a complete — OCR engine improvements"
```
