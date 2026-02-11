"""SQLite 세션 저장소 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from aion2meter.io.session_repository import SessionRepository
from aion2meter.models import DamageEvent, DpsSnapshot, HitType


def _sample_events() -> list[DamageEvent]:
    return [
        DamageEvent(
            timestamp=1000.0,
            source="플레이어",
            target="몬스터A",
            skill="검격",
            damage=1500,
            hit_type=HitType.NORMAL,
        ),
        DamageEvent(
            timestamp=1001.0,
            source="플레이어",
            target="몬스터A",
            skill="마법",
            damage=3200,
            hit_type=HitType.CRITICAL,
        ),
        DamageEvent(
            timestamp=1002.0,
            source="플레이어",
            target="몬스터A",
            skill="검격",
            damage=800,
            hit_type=HitType.NORMAL,
            is_additional=True,
        ),
    ]


def _sample_snapshot() -> DpsSnapshot:
    return DpsSnapshot(
        dps=2750.0,
        total_damage=5500,
        elapsed_seconds=2.0,
        peak_dps=2750.0,
        combat_active=False,
        skill_breakdown={"검격": 2300, "마법": 3200},
        event_count=3,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> SessionRepository:
    return SessionRepository(db_path=tmp_path / "sessions.db")


class TestSaveSession:
    """save_session 검증."""

    def test_returns_int_id(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        assert isinstance(sid, int)

    def test_multiple_saves_increasing_ids(self, repo: SessionRepository) -> None:
        id1 = repo.save_session(_sample_events(), _sample_snapshot())
        id2 = repo.save_session(_sample_events(), _sample_snapshot())
        assert id2 > id1


class TestListSessions:
    """list_sessions 검증."""

    def test_empty_list(self, repo: SessionRepository) -> None:
        result = repo.list_sessions()
        assert result == []

    def test_returns_saved(self, repo: SessionRepository) -> None:
        repo.save_session(_sample_events(), _sample_snapshot())
        result = repo.list_sessions()
        assert len(result) == 1

    def test_newest_first_order(self, repo: SessionRepository) -> None:
        events1 = [
            DamageEvent(
                timestamp=500.0,
                source="플레이어",
                target="몬스터A",
                skill="검격",
                damage=100,
                hit_type=HitType.NORMAL,
            ),
        ]
        snap1 = DpsSnapshot(
            dps=100.0,
            total_damage=100,
            elapsed_seconds=1.0,
            peak_dps=100.0,
            combat_active=False,
            event_count=1,
        )
        events2 = _sample_events()
        snap2 = _sample_snapshot()

        repo.save_session(events1, snap1)
        repo.save_session(events2, snap2)

        result = repo.list_sessions()
        assert len(result) == 2
        assert result[0]["start_time"] > result[1]["start_time"]

    def test_limit_parameter(self, repo: SessionRepository) -> None:
        for _ in range(5):
            repo.save_session(_sample_events(), _sample_snapshot())
        result = repo.list_sessions(limit=3)
        assert len(result) == 3


class TestGetSession:
    """get_session 검증."""

    def test_existing_session(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        session = repo.get_session(sid)
        assert session is not None
        assert session["id"] == sid
        assert session["total_damage"] == 5500
        assert session["peak_dps"] == 2750.0

    def test_nonexistent_returns_none(self, repo: SessionRepository) -> None:
        result = repo.get_session(9999)
        assert result is None


class TestGetSessionEvents:
    """get_session_events 검증."""

    def test_events_saved_correctly(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        events = repo.get_session_events(sid)
        assert len(events) == 3
        assert events[0]["timestamp"] == 1000.0
        assert events[0]["skill"] == "검격"
        assert events[0]["damage"] == 1500
        assert events[1]["hit_type"] == "치명타"
        assert events[2]["is_additional"] == 1


class TestGetSkillSummary:
    """get_skill_summary 검증."""

    def test_skill_aggregation(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        summary = repo.get_skill_summary(sid)
        assert len(summary) == 2
        # 총 대미지 내림차순: 마법(3200) > 검격(2300)
        assert summary[0]["skill"] == "마법"
        assert summary[0]["total_damage"] == 3200
        assert summary[0]["hit_count"] == 1
        assert summary[1]["skill"] == "검격"
        assert summary[1]["total_damage"] == 2300
        assert summary[1]["hit_count"] == 2


class TestDeleteSession:
    """delete_session 검증."""

    def test_delete_removes_session(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        repo.delete_session(sid)
        assert repo.get_session(sid) is None

    def test_delete_cascades_events(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        repo.delete_session(sid)
        assert repo.get_session_events(sid) == []

    def test_delete_cascades_skill_summary(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        repo.delete_session(sid)
        assert repo.get_skill_summary(sid) == []


class TestSessionTimeline:
    """session_timeline 테이블 검증."""

    def test_save_includes_timeline(self, repo: SessionRepository) -> None:
        snap = DpsSnapshot(
            dps=2750.0,
            total_damage=5500,
            elapsed_seconds=2.0,
            peak_dps=2750.0,
            combat_active=False,
            skill_breakdown={"검격": 2300, "마법": 3200},
            event_count=3,
            dps_timeline=[(0.0, 1500.0), (1.0, 2350.0), (2.0, 2750.0)],
        )
        sid = repo.save_session(_sample_events(), snap)
        timeline = repo.get_session_timeline(sid)
        assert len(timeline) == 3

    def test_timeline_values(self, repo: SessionRepository) -> None:
        snap = DpsSnapshot(
            dps=1000.0,
            total_damage=2000,
            elapsed_seconds=2.0,
            peak_dps=1200.0,
            combat_active=False,
            event_count=2,
            dps_timeline=[(0.0, 1200.0), (2.0, 1000.0)],
        )
        sid = repo.save_session(_sample_events(), snap)
        timeline = repo.get_session_timeline(sid)
        assert timeline[0]["elapsed"] == pytest.approx(0.0)
        assert timeline[0]["dps"] == pytest.approx(1200.0)
        assert timeline[1]["elapsed"] == pytest.approx(2.0)

    def test_timeline_empty_when_no_data(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        timeline = repo.get_session_timeline(sid)
        assert timeline == []

    def test_timeline_deleted_on_cascade(self, repo: SessionRepository) -> None:
        snap = DpsSnapshot(
            dps=1000.0,
            total_damage=1000,
            elapsed_seconds=1.0,
            peak_dps=1000.0,
            combat_active=False,
            event_count=1,
            dps_timeline=[(0.0, 1000.0)],
        )
        sid = repo.save_session(_sample_events(), snap)
        repo.delete_session(sid)
        timeline = repo.get_session_timeline(sid)
        assert timeline == []


class TestSessionTag:
    """세션 태그 기능 검증."""

    def test_save_with_tag(self, repo: SessionRepository) -> None:
        """태그와 함께 세션을 저장하면 tag가 기록된다."""
        sid = repo.save_session(_sample_events(), _sample_snapshot(), tag="보스1")
        session = repo.get_session(sid)
        assert session is not None
        assert session["tag"] == "보스1"

    def test_save_without_tag_defaults_empty(self, repo: SessionRepository) -> None:
        """태그 없이 저장하면 빈 문자열이다."""
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        session = repo.get_session(sid)
        assert session is not None
        assert session["tag"] == ""

    def test_list_sessions_includes_tag(self, repo: SessionRepository) -> None:
        """목록에 tag 필드가 포함된다."""
        repo.save_session(_sample_events(), _sample_snapshot(), tag="테스트")
        sessions = repo.list_sessions()
        assert sessions[0]["tag"] == "테스트"

    def test_filter_by_tag(self, repo: SessionRepository) -> None:
        """tag_filter로 필터링한다."""
        repo.save_session(_sample_events(), _sample_snapshot(), tag="보스A")
        repo.save_session(_sample_events(), _sample_snapshot(), tag="보스B")
        repo.save_session(_sample_events(), _sample_snapshot(), tag="")

        result = repo.list_sessions(tag_filter="보스A")
        assert len(result) == 1
        assert result[0]["tag"] == "보스A"

    def test_filter_empty_returns_all(self, repo: SessionRepository) -> None:
        """빈 필터는 전체를 반환한다."""
        repo.save_session(_sample_events(), _sample_snapshot(), tag="보스")
        repo.save_session(_sample_events(), _sample_snapshot())
        result = repo.list_sessions(tag_filter="")
        assert len(result) == 2

    def test_migration_adds_tag_column(self, tmp_path: Path) -> None:
        """기존 DB에 tag 컬럼이 없으면 마이그레이션한다."""
        db_path = tmp_path / "old.db"
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        # tag 컬럼 없는 스키마로 테이블 생성
        conn.execute("""CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time REAL NOT NULL,
            end_time REAL,
            total_damage INTEGER DEFAULT 0,
            peak_dps REAL DEFAULT 0.0,
            avg_dps REAL DEFAULT 0.0,
            event_count INTEGER DEFAULT 0,
            duration REAL DEFAULT 0.0
        )""")
        conn.execute(
            "INSERT INTO sessions (start_time, end_time, total_damage) VALUES (1.0, 2.0, 100)"
        )
        conn.commit()
        conn.close()

        # SessionRepository가 마이그레이션을 수행해야 한다
        repo = SessionRepository(db_path=db_path)
        sessions = repo.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["tag"] == ""
