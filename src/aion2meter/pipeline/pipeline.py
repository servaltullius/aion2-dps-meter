"""캡처 → OCR → 파싱 → DPS 계산 파이프라인."""

from __future__ import annotations

import logging
import queue
import time

logger = logging.getLogger(__name__)

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from aion2meter.calculator.dps_calculator import RealtimeDpsCalculator
from aion2meter.capture.mss_capture import MssCapture
from aion2meter.models import AppConfig, CapturedFrame, DpsSnapshot, ROI
from aion2meter.ocr.engine_manager import OcrEngineManager
from aion2meter.parser.combat_parser import KoreanCombatParser
from aion2meter.preprocess.image_proc import CombatLogPreprocessor


class CaptureWorker(QThread):
    """화면 캡처 워커 스레드."""

    frame_captured = pyqtSignal(object)  # CapturedFrame

    def __init__(self, capturer: MssCapture, roi: ROI, fps: int = 10) -> None:
        super().__init__()
        self._capturer = capturer
        self._roi = roi
        self._fps = fps
        self._running = False

    def run(self) -> None:
        self._running = True
        interval = 1.0 / self._fps
        while self._running:
            start = time.monotonic()
            try:
                frame = self._capturer.capture(self._roi)
                self.frame_captured.emit(frame)
            except Exception:
                logger.warning("캡처 실패", exc_info=True)
            elapsed = time.monotonic() - start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self) -> None:
        self._running = False

    def update_roi(self, roi: ROI) -> None:
        self._roi = roi


class OcrWorker(QThread):
    """OCR 처리 워커 스레드."""

    dps_updated = pyqtSignal(object)  # DpsSnapshot

    def __init__(
        self,
        preprocessor: CombatLogPreprocessor,
        ocr_engine: OcrEngineManager,
        parser: KoreanCombatParser,
        calculator: RealtimeDpsCalculator,
        max_queue_size: int = 2,
    ) -> None:
        super().__init__()
        self._preprocessor = preprocessor
        self._ocr_engine = ocr_engine
        self._parser = parser
        self._calculator = calculator
        self._queue: queue.Queue[CapturedFrame] = queue.Queue(maxsize=max_queue_size)
        self._running = False

    def enqueue(self, frame: CapturedFrame) -> None:
        """프레임을 큐에 추가. 큐가 꽉 차면 가장 오래된 프레임 버림."""
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(frame)
            except queue.Full:
                logger.debug("프레임 큐 오버플로우")

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                frame = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # 큐에 더 있으면 최신만 처리 (stale 프레임 스킵)
            while not self._queue.empty():
                try:
                    frame = self._queue.get_nowait()
                except queue.Empty:
                    break

            if self._preprocessor.is_duplicate(frame):
                continue

            processed = self._preprocessor.process(frame)
            ocr_result = self._ocr_engine.recognize(processed)

            if not ocr_result.text.strip():
                continue

            events = self._parser.parse(ocr_result.text, frame.timestamp)
            if events:
                snapshot = self._calculator.add_events(events)
                self.dps_updated.emit(snapshot)

    def stop(self) -> None:
        self._running = False


class DpsPipeline(QObject):
    """DPS 파이프라인 조립 및 제어."""

    dps_updated = pyqtSignal(object)  # DpsSnapshot

    def __init__(
        self,
        config: AppConfig,
        capturer: MssCapture | None = None,
        ocr_engine: OcrEngineManager | None = None,
    ) -> None:
        super().__init__()
        self._config = config

        self._capturer = capturer or MssCapture()
        self._preprocessor = CombatLogPreprocessor(
            config.color_ranges or AppConfig.default_color_ranges()
        )
        self._ocr_engine = ocr_engine or OcrEngineManager(primary=self._build_default_ocr())
        self._parser = KoreanCombatParser()
        self._calculator = RealtimeDpsCalculator(idle_timeout=config.idle_timeout)

        self._capture_worker: CaptureWorker | None = None
        self._ocr_worker: OcrWorker | None = None

    def _build_default_ocr(self) -> object:
        """기본 OCR 엔진 생성. winocr 우선, 없으면 tesseract."""
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
        raise RuntimeError("사용 가능한 OCR 엔진이 없습니다. winocr 또는 pytesseract를 설치하세요.")

    def start(self, roi: ROI) -> None:
        """파이프라인 시작."""
        if self._capture_worker is not None:
            self.stop()

        self._ocr_worker = OcrWorker(
            preprocessor=self._preprocessor,
            ocr_engine=self._ocr_engine,
            parser=self._parser,
            calculator=self._calculator,
        )
        self._ocr_worker.dps_updated.connect(self.dps_updated.emit)

        self._capture_worker = CaptureWorker(
            capturer=self._capturer,
            roi=roi,
            fps=self._config.fps,
        )
        self._capture_worker.frame_captured.connect(self._ocr_worker.enqueue)

        self._ocr_worker.start()
        self._capture_worker.start()

    def stop(self) -> None:
        """파이프라인 정지."""
        if self._capture_worker is not None:
            self._capture_worker.stop()
            self._capture_worker.wait(2000)
            self._capture_worker = None

        if self._ocr_worker is not None:
            self._ocr_worker.stop()
            self._ocr_worker.wait(2000)
            self._ocr_worker = None

    def update_roi(self, roi: ROI) -> None:
        """실행 중 ROI 변경."""
        if self._capture_worker is not None:
            self._capture_worker.update_roi(roi)

    def reset_combat(self) -> None:
        """전투 데이터 리셋."""
        self._calculator.reset()

    def get_event_history(self) -> list:
        """현재 전투의 이벤트 히스토리를 반환한다."""
        return self._calculator.get_event_history()

    @property
    def is_running(self) -> bool:
        return self._capture_worker is not None and self._capture_worker.isRunning()
