"""DPS 알림 단위 테스트."""

from __future__ import annotations

import pytest

from aion2meter.alert_manager import AlertEvent, AlertManager
from aion2meter.models import DpsSnapshot


def _snap(dps: float) -> DpsSnapshot:
    return DpsSnapshot(
        dps=dps,
        total_damage=int(dps * 10),
        elapsed_seconds=10.0,
        peak_dps=dps,
        combat_active=True,
        event_count=10,
    )


class TestAlertManager:
    """AlertManager 검증."""

    def test_above_threshold(self) -> None:
        """DPS가 임계값을 초과하면 'above' 알림."""
        mgr = AlertManager(threshold=5000.0)
        alert = mgr.check(_snap(6000.0))
        assert alert is not None
        assert alert.alert_type == "above"
        assert alert.current_dps == 6000.0

    def test_below_threshold(self) -> None:
        """DPS가 임계값 아래로 떨어지면 'below' 알림."""
        mgr = AlertManager(threshold=5000.0)
        mgr.check(_snap(6000.0))  # above 발생
        alert = mgr.check(_snap(4000.0))
        assert alert is not None
        assert alert.alert_type == "below"

    def test_cooldown_suppresses(self) -> None:
        """쿨다운 시간 내 같은 유형은 억제된다."""
        mgr = AlertManager(threshold=5000.0, cooldown=10.0)
        mgr.check(_snap(6000.0))  # above 발생
        alert = mgr.check(_snap(7000.0))  # 쿨다운 내
        assert alert is None

    def test_disabled_when_zero(self) -> None:
        """threshold가 0이면 알림 비활성."""
        mgr = AlertManager(threshold=0.0)
        alert = mgr.check(_snap(99999.0))
        assert alert is None

    def test_no_alert_when_staying_below(self) -> None:
        """처음부터 임계값 아래면 알림 없음."""
        mgr = AlertManager(threshold=5000.0)
        alert = mgr.check(_snap(3000.0))
        assert alert is None

    def test_alert_event_fields(self) -> None:
        """AlertEvent가 올바른 필드를 가진다."""
        evt = AlertEvent(
            alert_type="above",
            threshold=5000.0,
            current_dps=6000.0,
            timestamp=1234.0,
        )
        assert evt.alert_type == "above"
        assert evt.threshold == 5000.0
