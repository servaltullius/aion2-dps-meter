"""전투 로그 내보내기 단위 테스트."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from aion2meter.io.combat_logger import CombatLogExporter
from aion2meter.models import DamageEvent, HitType


def _sample_events() -> list[DamageEvent]:
    return [
        DamageEvent(
            timestamp=1000.0,
            source="플레이어",
            target="몬스터A",
            skill="검격",
            damage=1500,
            hit_type=HitType.NORMAL,
            is_additional=False,
        ),
        DamageEvent(
            timestamp=1001.5,
            source="플레이어",
            target="몬스터B",
            skill="마법",
            damage=3200,
            hit_type=HitType.CRITICAL,
            is_additional=False,
        ),
        DamageEvent(
            timestamp=1001.5,
            source="플레이어",
            target="몬스터B",
            skill="마법",
            damage=800,
            hit_type=HitType.NORMAL,
            is_additional=True,
        ),
    ]


class TestCsvExport:
    """CSV 내보내기 검증."""

    def test_csv_creates_file(self, tmp_path: Path) -> None:
        filepath = tmp_path / "test.csv"
        CombatLogExporter.export_csv(_sample_events(), filepath)
        assert filepath.exists()

    def test_csv_has_header(self, tmp_path: Path) -> None:
        filepath = tmp_path / "test.csv"
        CombatLogExporter.export_csv(_sample_events(), filepath)
        with open(filepath, encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert header == [
            "timestamp", "source", "target", "skill",
            "damage", "hit_type", "is_additional",
        ]

    def test_csv_row_count(self, tmp_path: Path) -> None:
        filepath = tmp_path / "test.csv"
        events = _sample_events()
        CombatLogExporter.export_csv(events, filepath)
        with open(filepath, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert len(rows) == len(events) + 1  # header + data

    def test_csv_data_values(self, tmp_path: Path) -> None:
        filepath = tmp_path / "test.csv"
        CombatLogExporter.export_csv(_sample_events(), filepath)
        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            first = next(reader)
        assert first["skill"] == "검격"
        assert first["damage"] == "1500"
        assert first["hit_type"] == "일반"
        assert first["is_additional"] == "False"

    def test_csv_creates_parent_dirs(self, tmp_path: Path) -> None:
        filepath = tmp_path / "sub" / "dir" / "test.csv"
        CombatLogExporter.export_csv(_sample_events(), filepath)
        assert filepath.exists()

    def test_csv_empty_events(self, tmp_path: Path) -> None:
        filepath = tmp_path / "empty.csv"
        CombatLogExporter.export_csv([], filepath)
        with open(filepath, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert len(rows) == 1  # header only


class TestJsonExport:
    """JSON 내보내기 검증."""

    def test_json_creates_file(self, tmp_path: Path) -> None:
        filepath = tmp_path / "test.json"
        CombatLogExporter.export_json(_sample_events(), filepath)
        assert filepath.exists()

    def test_json_is_valid(self, tmp_path: Path) -> None:
        filepath = tmp_path / "test.json"
        CombatLogExporter.export_json(_sample_events(), filepath)
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)

    def test_json_event_count(self, tmp_path: Path) -> None:
        filepath = tmp_path / "test.json"
        events = _sample_events()
        CombatLogExporter.export_json(events, filepath)
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == len(events)

    def test_json_data_values(self, tmp_path: Path) -> None:
        filepath = tmp_path / "test.json"
        CombatLogExporter.export_json(_sample_events(), filepath)
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        first = data[0]
        assert first["skill"] == "검격"
        assert first["damage"] == 1500
        assert first["hit_type"] == "일반"
        assert first["is_additional"] is False

    def test_json_korean_encoding(self, tmp_path: Path) -> None:
        filepath = tmp_path / "test.json"
        CombatLogExporter.export_json(_sample_events(), filepath)
        raw = filepath.read_text(encoding="utf-8")
        assert "플레이어" in raw  # ensure_ascii=False 확인

    def test_json_creates_parent_dirs(self, tmp_path: Path) -> None:
        filepath = tmp_path / "a" / "b" / "test.json"
        CombatLogExporter.export_json(_sample_events(), filepath)
        assert filepath.exists()

    def test_json_empty_events(self, tmp_path: Path) -> None:
        filepath = tmp_path / "empty.json"
        CombatLogExporter.export_json([], filepath)
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        assert data == []
