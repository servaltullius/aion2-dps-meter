"""SQLite 세션 저장소."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

from aion2meter.models import DamageEvent, DpsSnapshot

_DEFAULT_DB_PATH = Path.home() / ".aion2meter" / "sessions.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time  REAL NOT NULL,
    end_time    REAL,
    total_damage INTEGER DEFAULT 0,
    peak_dps    REAL DEFAULT 0.0,
    avg_dps     REAL DEFAULT 0.0,
    event_count INTEGER DEFAULT 0,
    duration    REAL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS session_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    timestamp   REAL NOT NULL,
    source      TEXT NOT NULL,
    target      TEXT NOT NULL,
    skill       TEXT NOT NULL,
    damage      INTEGER NOT NULL,
    hit_type    TEXT NOT NULL,
    is_additional INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS skill_summaries (
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    skill       TEXT NOT NULL,
    total_damage INTEGER NOT NULL,
    hit_count   INTEGER NOT NULL,
    PRIMARY KEY (session_id, skill)
);
CREATE TABLE IF NOT EXISTS session_timeline (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    elapsed     REAL NOT NULL,
    dps         REAL NOT NULL
);
"""


class SessionRepository:
    """전투 세션을 SQLite에 저장하고 조회한다."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)

    def save_session(
        self, events: list[DamageEvent], snapshot: DpsSnapshot
    ) -> int:
        """세션, 이벤트, 스킬 요약을 저장하고 세션 ID를 반환한다."""
        start_time = events[0].timestamp if events else 0.0
        end_time = events[-1].timestamp if events else 0.0
        duration = snapshot.elapsed_seconds
        avg_dps = snapshot.dps

        cur = self._conn.execute(
            "INSERT INTO sessions "
            "(start_time, end_time, total_damage, peak_dps, avg_dps, event_count, duration) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                start_time,
                end_time,
                snapshot.total_damage,
                snapshot.peak_dps,
                avg_dps,
                snapshot.event_count,
                duration,
            ),
        )
        session_id: int = cur.lastrowid  # type: ignore[assignment]

        # 이벤트 일괄 삽입
        self._conn.executemany(
            "INSERT INTO session_events "
            "(session_id, timestamp, source, target, skill, damage, hit_type, is_additional) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    session_id,
                    e.timestamp,
                    e.source,
                    e.target,
                    e.skill,
                    e.damage,
                    e.hit_type.value,
                    int(e.is_additional),
                )
                for e in events
            ],
        )

        # 스킬 요약 계산 및 삽입
        skill_agg: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total_damage": 0, "hit_count": 0}
        )
        for e in events:
            skill_agg[e.skill]["total_damage"] += e.damage
            skill_agg[e.skill]["hit_count"] += 1

        self._conn.executemany(
            "INSERT INTO skill_summaries "
            "(session_id, skill, total_damage, hit_count) "
            "VALUES (?, ?, ?, ?)",
            [
                (session_id, skill, agg["total_damage"], agg["hit_count"])
                for skill, agg in skill_agg.items()
            ],
        )

        # 타임라인 삽입
        if snapshot.dps_timeline:
            self._conn.executemany(
                "INSERT INTO session_timeline "
                "(session_id, elapsed, dps) "
                "VALUES (?, ?, ?)",
                [
                    (session_id, elapsed, dps)
                    for elapsed, dps in snapshot.dps_timeline
                ],
            )

        self._conn.commit()
        return session_id

    def list_sessions(self, limit: int = 50) -> list[dict]:
        """세션 목록을 최신 순으로 반환한다."""
        cur = self._conn.execute(
            "SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_session(self, session_id: int) -> dict | None:
        """세션 ID로 단일 세션을 조회한다."""
        cur = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_session_events(self, session_id: int) -> list[dict]:
        """세션의 이벤트를 시간순으로 반환한다."""
        cur = self._conn.execute(
            "SELECT * FROM session_events WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_skill_summary(self, session_id: int) -> list[dict]:
        """세션의 스킬 요약을 총 대미지 내림차순으로 반환한다."""
        cur = self._conn.execute(
            "SELECT * FROM skill_summaries "
            "WHERE session_id = ? ORDER BY total_damage DESC",
            (session_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def delete_session(self, session_id: int) -> None:
        """세션과 관련 데이터를 삭제한다 (CASCADE)."""
        self._conn.execute(
            "DELETE FROM sessions WHERE id = ?", (session_id,)
        )
        self._conn.commit()

    def get_session_timeline(self, session_id: int) -> list[dict]:
        """세션의 DPS 타임라인을 시간순으로 반환한다."""
        cur = self._conn.execute(
            "SELECT * FROM session_timeline "
            "WHERE session_id = ? ORDER BY elapsed",
            (session_id,),
        )
        return [dict(row) for row in cur.fetchall()]
