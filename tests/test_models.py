"""모델 단위 테스트."""

import pytest

from aion2meter.models import (
    ROI,
    AppConfig,
    ColorRange,
    DamageEvent,
    DpsSnapshot,
    HitType,
    OcrResult,
)


class TestROI:
    def test_valid_roi(self):
        roi = ROI(left=100, top=200, width=800, height=600)
        assert roi.left == 100
        assert roi.as_dict() == {"left": 100, "top": 200, "width": 800, "height": 600}

    def test_negative_width_raises(self):
        with pytest.raises(ValueError, match="양수"):
            ROI(left=0, top=0, width=-1, height=100)

    def test_zero_height_raises(self):
        with pytest.raises(ValueError, match="양수"):
            ROI(left=0, top=0, width=100, height=0)

    def test_negative_position_raises(self):
        with pytest.raises(ValueError, match="0 이상"):
            ROI(left=-1, top=0, width=100, height=100)

    def test_frozen(self):
        roi = ROI(left=0, top=0, width=100, height=100)
        with pytest.raises(AttributeError):
            roi.left = 10  # type: ignore[misc]


class TestColorRange:
    def test_create(self):
        cr = ColorRange("white", (182, 144, 100), (255, 200, 140))
        assert cr.name == "white"
        assert cr.lower == (182, 144, 100)


class TestDamageEvent:
    def test_default_hit_type(self):
        evt = DamageEvent(
            timestamp=1.0,
            source="플레이어",
            target="몬스터",
            skill="검격",
            damage=1000,
        )
        assert evt.hit_type == HitType.NORMAL
        assert evt.is_additional is False

    def test_critical_hit(self):
        evt = DamageEvent(
            timestamp=1.0,
            source="플레이어",
            target="몬스터",
            skill="검격",
            damage=2000,
            hit_type=HitType.CRITICAL,
        )
        assert evt.hit_type == HitType.CRITICAL


class TestDpsSnapshot:
    def test_defaults(self):
        snap = DpsSnapshot(
            dps=1500.0,
            total_damage=15000,
            elapsed_seconds=10.0,
            peak_dps=2000.0,
            combat_active=True,
        )
        assert snap.skill_breakdown == {}
        assert snap.event_count == 0

    def test_with_breakdown(self):
        snap = DpsSnapshot(
            dps=1000.0,
            total_damage=5000,
            elapsed_seconds=5.0,
            peak_dps=1500.0,
            combat_active=True,
            skill_breakdown={"검격": 3000, "마법": 2000},
            event_count=5,
        )
        assert snap.skill_breakdown["검격"] == 3000


class TestOcrResult:
    def test_create(self):
        r = OcrResult(text="테스트", confidence=0.95, timestamp=1.0)
        assert r.text == "테스트"


class TestAppConfig:
    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.roi is None
        assert cfg.fps == 10
        assert cfg.ocr_engine == "winocr"
        assert cfg.idle_timeout == 5.0

    def test_default_color_ranges(self):
        ranges = AppConfig.default_color_ranges()
        assert len(ranges) == 5
        assert ranges[0].name == "white"
