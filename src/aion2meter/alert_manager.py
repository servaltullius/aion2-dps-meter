"""DPS 임계값 알림."""

from __future__ import annotations

import time
from dataclasses import dataclass

from aion2meter.models import DpsSnapshot


@dataclass(frozen=True)
class AlertEvent:
    """DPS 알림 이벤트."""

    alert_type: str  # "above" | "below"
    threshold: float
    current_dps: float
    timestamp: float


class AlertManager:
    """DPS가 임계값을 초과/미달할 때 알림을 생성한다."""

    def __init__(self, threshold: float, cooldown: float = 10.0) -> None:
        self._threshold = threshold
        self._cooldown = cooldown
        self._was_above = False
        self._last_alert_time: dict[str, float] = {}

    def check(self, snapshot: DpsSnapshot) -> AlertEvent | None:
        """스냅샷을 확인하여 알림 이벤트를 반환한다."""
        if self._threshold <= 0:
            return None

        now = time.monotonic()
        is_above = snapshot.dps >= self._threshold

        if is_above and not self._was_above:
            self._was_above = True
            if self._is_cooled_down("above", now):
                self._last_alert_time["above"] = now
                return AlertEvent(
                    alert_type="above",
                    threshold=self._threshold,
                    current_dps=snapshot.dps,
                    timestamp=now,
                )
        elif not is_above and self._was_above:
            self._was_above = False
            if self._is_cooled_down("below", now):
                self._last_alert_time["below"] = now
                return AlertEvent(
                    alert_type="below",
                    threshold=self._threshold,
                    current_dps=snapshot.dps,
                    timestamp=now,
                )

        return None

    def _is_cooled_down(self, alert_type: str, now: float) -> bool:
        last = self._last_alert_time.get(alert_type, 0.0)
        return (now - last) >= self._cooldown
