"""Protocol 인터페이스 정의."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aion2meter.models import CapturedFrame, DamageEvent, DpsSnapshot, OcrResult, ROI


@runtime_checkable
class ScreenCapturer(Protocol):
    """화면 캡처 인터페이스."""

    def capture(self, roi: ROI) -> CapturedFrame: ...


@runtime_checkable
class ImagePreprocessor(Protocol):
    """이미지 전처리 인터페이스."""

    def process(self, frame: CapturedFrame) -> object:
        """전처리된 이미지(numpy ndarray)를 반환."""
        ...

    def is_duplicate(self, frame: CapturedFrame) -> bool:
        """이전 프레임과 동일한지 확인."""
        ...


@runtime_checkable
class OcrEngine(Protocol):
    """OCR 엔진 인터페이스."""

    def recognize(self, image: object) -> OcrResult: ...


@runtime_checkable
class CombatLogParser(Protocol):
    """전투 로그 파서 인터페이스."""

    def parse(self, text: str, timestamp: float) -> list[DamageEvent]: ...


@runtime_checkable
class DpsEngine(Protocol):
    """DPS 계산 엔진 인터페이스."""

    def add_events(self, events: list[DamageEvent]) -> DpsSnapshot: ...

    def reset(self) -> None: ...
