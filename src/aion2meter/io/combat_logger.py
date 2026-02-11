"""전투 로그 CSV/JSON 내보내기."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from aion2meter.models import DamageEvent


_CSV_COLUMNS = [
    "timestamp",
    "source",
    "target",
    "skill",
    "damage",
    "hit_type",
    "is_additional",
]


class CombatLogExporter:
    """DamageEvent 리스트를 CSV 또는 JSON으로 내보낸다."""

    @staticmethod
    def export_csv(events: list[DamageEvent], filepath: Path) -> None:
        """이벤트를 CSV 파일로 저장한다."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_CSV_COLUMNS)
            for e in events:
                writer.writerow([
                    e.timestamp,
                    e.source,
                    e.target,
                    e.skill,
                    e.damage,
                    e.hit_type.value,
                    e.is_additional,
                ])

    @staticmethod
    def export_json(events: list[DamageEvent], filepath: Path) -> None:
        """이벤트를 JSON 파일로 저장한다."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "timestamp": e.timestamp,
                "source": e.source,
                "target": e.target,
                "skill": e.skill,
                "damage": e.damage,
                "hit_type": e.hit_type.value,
                "is_additional": e.is_additional,
            }
            for e in events
        ]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
