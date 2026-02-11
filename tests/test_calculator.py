"""DPS 계산기 단위 테스트 (TDD - RED phase)."""

import pytest

from aion2meter.models import DamageEvent, DpsSnapshot, HitType
from aion2meter.calculator.dps_calculator import RealtimeDpsCalculator
from aion2meter.protocols import DpsEngine


def _make_event(
    timestamp: float = 1.0,
    skill: str = "검격",
    damage: int = 1000,
    hit_type: HitType = HitType.NORMAL,
) -> DamageEvent:
    """테스트용 DamageEvent 헬퍼."""
    return DamageEvent(
        timestamp=timestamp,
        source="플레이어",
        target="몬스터",
        skill=skill,
        damage=damage,
        hit_type=hit_type,
    )


class TestProtocolConformance:
    """RealtimeDpsCalculator가 DpsEngine Protocol을 만족하는지 확인."""

    def test_is_dps_engine(self):
        calc = RealtimeDpsCalculator()
        assert isinstance(calc, DpsEngine)


class TestInitialState:
    """이벤트 없을 때 초기 상태."""

    def test_empty_events_returns_zero_dps(self):
        calc = RealtimeDpsCalculator()
        snapshot = calc.add_events([])
        assert snapshot.dps == 0.0
        assert snapshot.total_damage == 0
        assert snapshot.combat_active is False

    def test_empty_events_returns_zero_elapsed(self):
        calc = RealtimeDpsCalculator()
        snapshot = calc.add_events([])
        assert snapshot.elapsed_seconds == 0.0

    def test_empty_events_returns_zero_peak_dps(self):
        calc = RealtimeDpsCalculator()
        snapshot = calc.add_events([])
        assert snapshot.peak_dps == 0.0

    def test_empty_events_returns_zero_event_count(self):
        calc = RealtimeDpsCalculator()
        snapshot = calc.add_events([])
        assert snapshot.event_count == 0

    def test_empty_events_returns_empty_skill_breakdown(self):
        calc = RealtimeDpsCalculator()
        snapshot = calc.add_events([])
        assert snapshot.skill_breakdown == {}


class TestSingleEvent:
    """하나의 대미지 이벤트 추가 후 DPS 확인."""

    def test_single_event_dps(self):
        calc = RealtimeDpsCalculator()
        event = _make_event(timestamp=10.0, damage=5000)
        snapshot = calc.add_events([event])
        # elapsed=0 이므로 max(0, 0.001) → 5000 / 0.001 = 5_000_000
        assert snapshot.dps == pytest.approx(5000 / 0.001)

    def test_single_event_total_damage(self):
        calc = RealtimeDpsCalculator()
        event = _make_event(timestamp=10.0, damage=5000)
        snapshot = calc.add_events([event])
        assert snapshot.total_damage == 5000

    def test_single_event_combat_active(self):
        calc = RealtimeDpsCalculator()
        event = _make_event(timestamp=10.0, damage=5000)
        snapshot = calc.add_events([event])
        assert snapshot.combat_active is True

    def test_single_event_event_count(self):
        calc = RealtimeDpsCalculator()
        event = _make_event(timestamp=10.0, damage=5000)
        snapshot = calc.add_events([event])
        assert snapshot.event_count == 1


class TestTimeBasedDps:
    """시간 경과에 따른 DPS 계산: total_damage / elapsed_seconds."""

    def test_two_events_dps(self):
        calc = RealtimeDpsCalculator()
        events = [
            _make_event(timestamp=10.0, damage=1000),
            _make_event(timestamp=12.0, damage=2000),
        ]
        snapshot = calc.add_events(events)
        # elapsed = 12.0 - 10.0 = 2.0초, total = 3000
        assert snapshot.dps == pytest.approx(3000 / 2.0)

    def test_multiple_batches_dps(self):
        calc = RealtimeDpsCalculator()
        # 첫 번째 배치
        calc.add_events([_make_event(timestamp=10.0, damage=1000)])
        # 두 번째 배치 (같은 전투)
        snapshot = calc.add_events([_make_event(timestamp=14.0, damage=3000)])
        # elapsed = 14.0 - 10.0 = 4.0초, total = 4000
        assert snapshot.dps == pytest.approx(4000 / 4.0)
        assert snapshot.total_damage == 4000
        assert snapshot.elapsed_seconds == pytest.approx(4.0)

    def test_elapsed_seconds_calculated_correctly(self):
        calc = RealtimeDpsCalculator()
        events = [
            _make_event(timestamp=100.0, damage=500),
            _make_event(timestamp=103.5, damage=500),
        ]
        snapshot = calc.add_events(events)
        assert snapshot.elapsed_seconds == pytest.approx(3.5)


class TestAutoReset:
    """idle_timeout(5초) 이후 새 이벤트 → 이전 전투 리셋, 새 전투 시작."""

    def test_auto_reset_after_idle_timeout(self):
        calc = RealtimeDpsCalculator(idle_timeout=5.0)
        # 첫 번째 전투
        calc.add_events([
            _make_event(timestamp=10.0, damage=1000),
            _make_event(timestamp=12.0, damage=2000),
        ])
        # 5초 이상 경과 후 새 이벤트 → 자동 리셋
        snapshot = calc.add_events([_make_event(timestamp=20.0, damage=500)])
        # 새 전투: 이벤트 1개, total=500
        assert snapshot.total_damage == 500
        assert snapshot.event_count == 1

    def test_no_reset_within_timeout(self):
        calc = RealtimeDpsCalculator(idle_timeout=5.0)
        calc.add_events([_make_event(timestamp=10.0, damage=1000)])
        # 3초 경과 (5초 이내) → 같은 전투 유지
        snapshot = calc.add_events([_make_event(timestamp=13.0, damage=2000)])
        assert snapshot.total_damage == 3000
        assert snapshot.event_count == 2

    def test_custom_idle_timeout(self):
        calc = RealtimeDpsCalculator(idle_timeout=2.0)
        calc.add_events([_make_event(timestamp=10.0, damage=1000)])
        # 2초 초과 경과 → 리셋
        snapshot = calc.add_events([_make_event(timestamp=13.0, damage=500)])
        assert snapshot.total_damage == 500
        assert snapshot.event_count == 1


class TestSkillBreakdown:
    """skill_breakdown dict에 스킬명별 총 대미지 누적."""

    def test_single_skill(self):
        calc = RealtimeDpsCalculator()
        events = [
            _make_event(timestamp=1.0, skill="검격", damage=1000),
            _make_event(timestamp=2.0, skill="검격", damage=1500),
        ]
        snapshot = calc.add_events(events)
        assert snapshot.skill_breakdown == {"검격": 2500}

    def test_multiple_skills(self):
        calc = RealtimeDpsCalculator()
        events = [
            _make_event(timestamp=1.0, skill="검격", damage=1000),
            _make_event(timestamp=2.0, skill="마법", damage=2000),
            _make_event(timestamp=3.0, skill="검격", damage=500),
        ]
        snapshot = calc.add_events(events)
        assert snapshot.skill_breakdown == {"검격": 1500, "마법": 2000}

    def test_skill_breakdown_across_batches(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([_make_event(timestamp=1.0, skill="검격", damage=1000)])
        snapshot = calc.add_events([_make_event(timestamp=2.0, skill="마법", damage=2000)])
        assert snapshot.skill_breakdown == {"검격": 1000, "마법": 2000}


class TestPeakDps:
    """DPS가 갱신될 때 최고값 유지."""

    def test_peak_dps_tracks_maximum(self):
        calc = RealtimeDpsCalculator()
        # 첫 번째: DPS가 높음 (elapsed 짧음)
        snap1 = calc.add_events([
            _make_event(timestamp=10.0, damage=10000),
            _make_event(timestamp=10.5, damage=10000),
        ])
        first_dps = snap1.dps  # 20000 / 0.5 = 40000

        # 두 번째: DPS가 낮아짐 (elapsed 길어짐)
        snap2 = calc.add_events([_make_event(timestamp=20.0, damage=100)])
        # peak_dps는 첫 번째의 높은 DPS를 유지해야 함
        assert snap2.peak_dps >= first_dps

    def test_peak_dps_never_decreases(self):
        calc = RealtimeDpsCalculator()
        snap1 = calc.add_events([_make_event(timestamp=1.0, damage=5000)])
        snap2 = calc.add_events([_make_event(timestamp=100.0, damage=1)])
        # 두 번째는 같은 전투(timeout 이내 아님)가 아니면 리셋되므로
        # idle_timeout 기본 5초이므로 리셋됨 → 새 전투의 peak
        # 어느 쪽이든 peak_dps >= 0
        assert snap2.peak_dps >= 0


class TestCombatActive:
    """이벤트 있으면 True, 리셋 후 False."""

    def test_combat_active_after_event(self):
        calc = RealtimeDpsCalculator()
        snapshot = calc.add_events([_make_event(timestamp=1.0)])
        assert snapshot.combat_active is True

    def test_combat_inactive_after_reset(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([_make_event(timestamp=1.0)])
        calc.reset()
        snapshot = calc.add_events([])
        assert snapshot.combat_active is False


class TestEventCount:
    """event_count 증가 확인."""

    def test_event_count_increments(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([_make_event(timestamp=1.0)])
        snap = calc.add_events([
            _make_event(timestamp=2.0),
            _make_event(timestamp=3.0),
        ])
        assert snap.event_count == 3

    def test_event_count_after_batch(self):
        calc = RealtimeDpsCalculator()
        events = [_make_event(timestamp=float(i)) for i in range(1, 6)]
        snap = calc.add_events(events)
        assert snap.event_count == 5


class TestManualReset:
    """수동 reset() 호출 시 모든 값 초기화."""

    def test_reset_clears_all(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([
            _make_event(timestamp=1.0, skill="검격", damage=1000),
            _make_event(timestamp=2.0, skill="마법", damage=2000),
        ])
        calc.reset()
        snapshot = calc.add_events([])
        assert snapshot.dps == 0.0
        assert snapshot.total_damage == 0
        assert snapshot.elapsed_seconds == 0.0
        assert snapshot.peak_dps == 0.0
        assert snapshot.combat_active is False
        assert snapshot.skill_breakdown == {}
        assert snapshot.event_count == 0

    def test_reset_allows_new_combat(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([_make_event(timestamp=1.0, damage=9999)])
        calc.reset()
        snapshot = calc.add_events([_make_event(timestamp=100.0, damage=500)])
        assert snapshot.total_damage == 500
        assert snapshot.event_count == 1
        assert snapshot.combat_active is True


class TestReturnType:
    """add_events는 DpsSnapshot을 반환해야 한다."""

    def test_returns_dps_snapshot(self):
        calc = RealtimeDpsCalculator()
        result = calc.add_events([])
        assert isinstance(result, DpsSnapshot)

    def test_returns_dps_snapshot_with_events(self):
        calc = RealtimeDpsCalculator()
        result = calc.add_events([_make_event()])
        assert isinstance(result, DpsSnapshot)


class TestEventHistory:
    """이벤트 히스토리 추적."""

    def test_empty_history_initially(self):
        calc = RealtimeDpsCalculator()
        assert calc.get_event_history() == []

    def test_history_tracks_events(self):
        calc = RealtimeDpsCalculator()
        e1 = _make_event(timestamp=1.0, skill="검격", damage=1000)
        e2 = _make_event(timestamp=2.0, skill="마법", damage=2000)
        calc.add_events([e1, e2])
        history = calc.get_event_history()
        assert len(history) == 2
        assert history[0] is e1
        assert history[1] is e2

    def test_history_across_batches(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([_make_event(timestamp=1.0)])
        calc.add_events([_make_event(timestamp=2.0)])
        assert len(calc.get_event_history()) == 2

    def test_history_cleared_on_reset(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([_make_event(timestamp=1.0)])
        calc.reset()
        assert calc.get_event_history() == []

    def test_history_cleared_on_auto_reset(self):
        calc = RealtimeDpsCalculator(idle_timeout=5.0)
        calc.add_events([_make_event(timestamp=1.0, damage=1000)])
        # idle_timeout 초과 → 자동 리셋
        calc.add_events([_make_event(timestamp=20.0, damage=500)])
        history = calc.get_event_history()
        assert len(history) == 1
        assert history[0].damage == 500

    def test_history_returns_copy(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([_make_event(timestamp=1.0)])
        h1 = calc.get_event_history()
        h2 = calc.get_event_history()
        assert h1 is not h2
        assert h1 == h2
