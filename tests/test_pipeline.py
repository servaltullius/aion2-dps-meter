"""파이프라인 단위 테스트 (mock 주입)."""

from __future__ import annotations

import queue
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from aion2meter.calculator.dps_calculator import RealtimeDpsCalculator
from aion2meter.models import (
    AppConfig,
    CapturedFrame,
    ColorRange,
    DamageEvent,
    DpsSnapshot,
    HitType,
    OcrResult,
    ROI,
)
from aion2meter.ocr.engine_manager import OcrEngineManager
from aion2meter.parser.combat_parser import KoreanCombatParser
from aion2meter.pipeline.pipeline import CaptureWorker, DpsPipeline, OcrWorker
from aion2meter.preprocess.image_proc import CombatLogPreprocessor


@pytest.fixture
def roi():
    return ROI(left=0, top=0, width=100, height=50)


@pytest.fixture
def sample_frame(roi):
    image = np.zeros((50, 100, 3), dtype=np.uint8)
    return CapturedFrame(image=image, timestamp=1.0, roi=roi)


class TestCaptureWorker:
    def test_stop_flag(self, roi):
        capturer = MagicMock()
        worker = CaptureWorker(capturer=capturer, roi=roi, fps=10)
        assert worker._running is False
        worker.stop()
        assert worker._running is False

    def test_update_roi(self, roi):
        capturer = MagicMock()
        worker = CaptureWorker(capturer=capturer, roi=roi, fps=10)
        new_roi = ROI(left=10, top=20, width=200, height=100)
        worker.update_roi(new_roi)
        assert worker._roi == new_roi


class TestOcrWorker:
    def test_enqueue_and_dequeue(self, sample_frame):
        preprocessor = MagicMock()
        ocr_engine = MagicMock()
        parser = MagicMock()
        calculator = MagicMock()

        worker = OcrWorker(
            preprocessor=preprocessor,
            ocr_engine=ocr_engine,
            parser=parser,
            calculator=calculator,
            max_queue_size=2,
        )
        worker.enqueue(sample_frame)
        assert worker._queue.qsize() == 1

    def test_enqueue_overflow_drops_oldest(self, sample_frame):
        preprocessor = MagicMock()
        ocr_engine = MagicMock()
        parser = MagicMock()
        calculator = MagicMock()

        worker = OcrWorker(
            preprocessor=preprocessor,
            ocr_engine=ocr_engine,
            parser=parser,
            calculator=calculator,
            max_queue_size=1,
        )
        worker.enqueue(sample_frame)
        # 큐가 꽉 찬 상태에서 추가 enqueue
        frame2 = CapturedFrame(
            image=np.ones((50, 100, 3), dtype=np.uint8),
            timestamp=2.0,
            roi=sample_frame.roi,
        )
        worker.enqueue(frame2)
        assert worker._queue.qsize() == 1


class TestDpsPipeline:
    def test_is_running_initially_false(self):
        config = AppConfig()
        capturer = MagicMock()
        ocr_engine = MagicMock()
        pipeline = DpsPipeline(config=config, capturer=capturer, ocr_engine=ocr_engine)
        assert pipeline.is_running is False

    def test_reset_combat(self):
        config = AppConfig()
        capturer = MagicMock()
        ocr_engine = MagicMock()
        pipeline = DpsPipeline(config=config, capturer=capturer, ocr_engine=ocr_engine)
        # reset_combat should not raise
        pipeline.reset_combat()
