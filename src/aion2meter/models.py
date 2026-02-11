"""Frozen dataclass 모델 정의."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class ROI:
    """화면 캡처 영역."""

    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"ROI 크기는 양수여야 합니다: {self.width}x{self.height}")
        if self.left < 0 or self.top < 0:
            raise ValueError(f"ROI 위치는 0 이상이어야 합니다: ({self.left}, {self.top})")

    def as_dict(self) -> dict[str, int]:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class ColorRange:
    """BGR 색상 범위."""

    name: str
    lower: tuple[int, int, int]  # BGR
    upper: tuple[int, int, int]  # BGR


@dataclass(frozen=True)
class CapturedFrame:
    """캡처된 프레임."""

    image: object  # numpy ndarray
    timestamp: float
    roi: ROI


class HitType(Enum):
    """공격 배율 유형."""

    NORMAL = "일반"
    PERFECT = "완벽"
    CRITICAL = "치명타"
    STRONG = "강타"
    STRONG_CRITICAL = "강타 치명타"
    PERFECT_CRITICAL = "완벽 치명타"


@dataclass(frozen=True)
class OcrResult:
    """OCR 결과."""

    text: str
    confidence: float
    timestamp: float


@dataclass(frozen=True)
class DamageEvent:
    """파싱된 대미지 이벤트."""

    timestamp: float
    source: str
    target: str
    skill: str
    damage: int
    hit_type: HitType = HitType.NORMAL
    is_additional: bool = False


@dataclass(frozen=True)
class DpsSnapshot:
    """특정 시점의 DPS 스냅샷."""

    dps: float
    total_damage: int
    elapsed_seconds: float
    peak_dps: float
    combat_active: bool
    skill_breakdown: dict[str, int] = field(default_factory=dict)
    event_count: int = 0
    dps_timeline: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class AppConfig:
    """앱 설정."""

    roi: ROI | None = None
    fps: int = 10
    ocr_engine: str = "winocr"
    idle_timeout: float = 5.0
    overlay_opacity: float = 0.75
    overlay_width: int = 220
    overlay_height: int = 120
    overlay_x: int | None = None
    overlay_y: int | None = None
    overlay_bg_color: tuple[int, int, int] = (0, 0, 0)
    hotkey_overlay: str = "<ctrl>+<shift>+o"
    hotkey_reset: str = "<ctrl>+<shift>+r"
    hotkey_breakdown: str = "<ctrl>+<shift>+b"
    auto_update_check: bool = True
    discord_webhook_url: str = ""
    discord_auto_send: bool = False
    dps_alert_threshold: float = 0.0
    dps_alert_cooldown: float = 10.0
    color_ranges: list[ColorRange] = field(default_factory=list)

    @classmethod
    def default_color_ranges(cls) -> list[ColorRange]:
        return [
            ColorRange("white", (182, 144, 100), (255, 200, 140)),
            ColorRange("orange", (0, 100, 200), (50, 180, 255)),
            ColorRange("red", (0, 0, 180), (80, 80, 255)),
            ColorRange("blue", (180, 100, 0), (255, 180, 80)),
            ColorRange("green", (0, 180, 0), (80, 255, 80)),
        ]
