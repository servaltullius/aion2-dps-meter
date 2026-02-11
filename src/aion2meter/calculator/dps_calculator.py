"""실시간 DPS 계산 엔진."""

from __future__ import annotations

from aion2meter.models import DamageEvent, DpsSnapshot

import logging
logger = logging.getLogger(__name__)


class RealtimeDpsCalculator:
    """DpsEngine Protocol을 구현하는 실시간 DPS 계산기.

    - 전투 시작: 첫 이벤트의 timestamp
    - 전투 종료 판정: 마지막 이벤트 timestamp + idle_timeout < 현재 이벤트 timestamp
    - DPS 계산: total_damage / max(elapsed_seconds, 0.001)
    """

    def __init__(self, idle_timeout: float = 5.0) -> None:
        self._idle_timeout = idle_timeout
        self._total_damage: int = 0
        self._event_count: int = 0
        self._peak_dps: float = 0.0
        self._skill_breakdown: dict[str, int] = {}
        self._first_timestamp: float | None = None
        self._last_timestamp: float | None = None
        self._event_history: list[DamageEvent] = []

    def add_events(self, events: list[DamageEvent]) -> DpsSnapshot:
        """이벤트 목록을 추가하고 현재 DPS 스냅샷을 반환한다."""
        for event in events:
            # 자동 리셋: 마지막 이벤트 이후 idle_timeout 초과 시
            if (
                self._last_timestamp is not None
                and event.timestamp > self._last_timestamp + self._idle_timeout
            ):
                self._reset_state()

            # 전투 시작 시점 기록
            if self._first_timestamp is None:
                self._first_timestamp = event.timestamp

            # 대미지 누적
            self._total_damage += event.damage
            self._event_count += 1
            self._last_timestamp = event.timestamp
            self._event_history.append(event)

            # 스킬별 분류
            self._skill_breakdown[event.skill] = (
                self._skill_breakdown.get(event.skill, 0) + event.damage
            )

        # 스냅샷 계산
        elapsed = self._calc_elapsed()
        dps = self._total_damage / max(elapsed, 0.001) if self._total_damage > 0 else 0.0
        combat_active = self._event_count > 0

        # peak DPS 갱신
        if dps > self._peak_dps:
            self._peak_dps = dps

        return DpsSnapshot(
            dps=dps,
            total_damage=self._total_damage,
            elapsed_seconds=elapsed,
            peak_dps=self._peak_dps,
            combat_active=combat_active,
            skill_breakdown=dict(self._skill_breakdown),
            event_count=self._event_count,
        )

    def get_event_history(self) -> list[DamageEvent]:
        """현재 전투의 이벤트 히스토리를 반환한다."""
        return list(self._event_history)

    def reset(self) -> None:
        """모든 상태를 초기화한다."""
        self._reset_state()

    def _reset_state(self) -> None:
        """내부 상태를 초기화한다."""
        logger.info("전투 리셋")
        self._total_damage = 0
        self._event_count = 0
        self._peak_dps = 0.0
        self._skill_breakdown = {}
        self._first_timestamp = None
        self._last_timestamp = None
        self._event_history = []

    def _calc_elapsed(self) -> float:
        """경과 시간(초)을 계산한다."""
        if self._first_timestamp is None or self._last_timestamp is None:
            return 0.0
        return self._last_timestamp - self._first_timestamp
