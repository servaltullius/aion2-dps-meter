# Phase 3+4 분석/리포트/배포 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** SQLite 세션 저장, matplotlib 차트 리포트, 세션 비교, 로깅, PyInstaller 빌드를 추가한다.

**Architecture:** SessionRepository가 SQLite로 전투 세션을 영구 저장한다. 전투가 자동 리셋(idle timeout)되거나 수동 리셋될 때 App이 세션을 저장한다. 리포트 UI는 matplotlib FigureCanvas를 PyQt6에 임베딩한다.

**Tech Stack:** sqlite3 (표준), logging (표준), matplotlib + matplotlib-backend-qtagg, PyInstaller

---

## Task F1: SQLite 세션 저장소

**Files:**
- Create: `src/aion2meter/io/session_repository.py`
- Modify: `src/aion2meter/io/__init__.py`
- Test: `tests/test_session_repository.py`

### Step 1: Write the failing tests

```python
# tests/test_session_repository.py
"""세션 저장소 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from aion2meter.io.session_repository import SessionRepository
from aion2meter.models import DamageEvent, DpsSnapshot, HitType


def _sample_events() -> list[DamageEvent]:
    return [
        DamageEvent(
            timestamp=1000.0, source="플레이어", target="몬스터A",
            skill="검격", damage=1500, hit_type=HitType.NORMAL,
        ),
        DamageEvent(
            timestamp=1001.0, source="플레이어", target="몬스터A",
            skill="마법", damage=3200, hit_type=HitType.CRITICAL,
        ),
        DamageEvent(
            timestamp=1002.0, source="플레이어", target="몬스터A",
            skill="검격", damage=800, hit_type=HitType.NORMAL, is_additional=True,
        ),
    ]


def _sample_snapshot() -> DpsSnapshot:
    return DpsSnapshot(
        dps=2750.0, total_damage=5500, elapsed_seconds=2.0,
        peak_dps=2750.0, combat_active=False,
        skill_breakdown={"검격": 2300, "마법": 3200}, event_count=3,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> SessionRepository:
    return SessionRepository(db_path=tmp_path / "test.db")


class TestSaveSession:
    def test_save_returns_id(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        assert isinstance(sid, int)
        assert sid >= 1

    def test_save_multiple_sessions(self, repo: SessionRepository) -> None:
        s1 = repo.save_session(_sample_events(), _sample_snapshot())
        s2 = repo.save_session(_sample_events(), _sample_snapshot())
        assert s2 > s1


class TestListSessions:
    def test_list_empty(self, repo: SessionRepository) -> None:
        assert repo.list_sessions() == []

    def test_list_returns_saved(self, repo: SessionRepository) -> None:
        repo.save_session(_sample_events(), _sample_snapshot())
        sessions = repo.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["total_damage"] == 5500

    def test_list_order_newest_first(self, repo: SessionRepository) -> None:
        repo.save_session(_sample_events(), _sample_snapshot())
        events2 = [DamageEvent(
            timestamp=2000.0, source="플레이어", target="보스",
            skill="궁극기", damage=9999, hit_type=HitType.PERFECT_CRITICAL,
        )]
        snap2 = DpsSnapshot(
            dps=9999.0, total_damage=9999, elapsed_seconds=1.0,
            peak_dps=9999.0, combat_active=False, event_count=1,
        )
        repo.save_session(events2, snap2)
        sessions = repo.list_sessions()
        assert len(sessions) == 2
        assert sessions[0]["total_damage"] == 9999  # newest first

    def test_list_limit(self, repo: SessionRepository) -> None:
        for _ in range(5):
            repo.save_session(_sample_events(), _sample_snapshot())
        assert len(repo.list_sessions(limit=3)) == 3


class TestGetSession:
    def test_get_existing(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        session = repo.get_session(sid)
        assert session is not None
        assert session["id"] == sid
        assert session["peak_dps"] == 2750.0

    def test_get_nonexistent(self, repo: SessionRepository) -> None:
        assert repo.get_session(999) is None


class TestGetSessionEvents:
    def test_events_saved(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        events = repo.get_session_events(sid)
        assert len(events) == 3
        assert events[0]["skill"] == "검격"
        assert events[1]["damage"] == 3200


class TestGetSkillSummary:
    def test_skill_summary(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        summary = repo.get_skill_summary(sid)
        assert len(summary) == 2
        skills = {s["skill"]: s for s in summary}
        assert skills["검격"]["total_damage"] == 2300
        assert skills["검격"]["hit_count"] == 2
        assert skills["마법"]["total_damage"] == 3200


class TestDeleteSession:
    def test_delete(self, repo: SessionRepository) -> None:
        sid = repo.save_session(_sample_events(), _sample_snapshot())
        repo.delete_session(sid)
        assert repo.get_session(sid) is None
        assert repo.list_sessions() == []
```

### Step 2: Run tests to verify they fail

Run: `python3 -m pytest tests/test_session_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'aion2meter.io.session_repository'`

### Step 3: Write the implementation

```python
# src/aion2meter/io/session_repository.py
"""SQLite 기반 전투 세션 저장소."""

from __future__ import annotations

import sqlite3
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
"""


class SessionRepository:
    """전투 세션을 SQLite에 저장/조회한다."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)

    def save_session(self, events: list[DamageEvent], snapshot: DpsSnapshot) -> int:
        """전투 세션을 저장하고 세션 ID를 반환한다."""
        if not events:
            # 이벤트 없어도 스냅샷 정보로 저장
            start_time = 0.0
            end_time = 0.0
        else:
            start_time = events[0].timestamp
            end_time = events[-1].timestamp

        cur = self._conn.execute(
            "INSERT INTO sessions (start_time, end_time, total_damage, peak_dps, avg_dps, event_count, duration) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (start_time, end_time, snapshot.total_damage, snapshot.peak_dps,
             snapshot.dps, snapshot.event_count, snapshot.elapsed_seconds),
        )
        session_id = cur.lastrowid

        # 이벤트 저장
        self._conn.executemany(
            "INSERT INTO session_events (session_id, timestamp, source, target, skill, damage, hit_type, is_additional) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(session_id, e.timestamp, e.source, e.target, e.skill,
              e.damage, e.hit_type.value, int(e.is_additional)) for e in events],
        )

        # 스킬 집계
        skill_map: dict[str, dict] = {}
        for e in events:
            if e.skill not in skill_map:
                skill_map[e.skill] = {"total_damage": 0, "hit_count": 0}
            skill_map[e.skill]["total_damage"] += e.damage
            skill_map[e.skill]["hit_count"] += 1

        self._conn.executemany(
            "INSERT INTO skill_summaries (session_id, skill, total_damage, hit_count) VALUES (?, ?, ?, ?)",
            [(session_id, skill, d["total_damage"], d["hit_count"]) for skill, d in skill_map.items()],
        )

        self._conn.commit()
        return session_id

    def list_sessions(self, limit: int = 50) -> list[dict]:
        """세션 목록을 최신순으로 반환한다."""
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: int) -> dict | None:
        """세션 상세 정보를 반환한다."""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_session_events(self, session_id: int) -> list[dict]:
        """세션의 이벤트 목록을 반환한다."""
        rows = self._conn.execute(
            "SELECT * FROM session_events WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_skill_summary(self, session_id: int) -> list[dict]:
        """세션의 스킬별 집계를 반환한다."""
        rows = self._conn.execute(
            "SELECT * FROM skill_summaries WHERE session_id = ? ORDER BY total_damage DESC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: int) -> None:
        """세션과 관련 데이터를 삭제한다."""
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()
```

### Step 4: Update `src/aion2meter/io/__init__.py`

```python
"""전투 로그 입출력 모듈."""

from aion2meter.io.combat_logger import CombatLogExporter
from aion2meter.io.session_repository import SessionRepository

__all__ = ["CombatLogExporter", "SessionRepository"]
```

### Step 5: Run tests to verify they pass

Run: `python3 -m pytest tests/test_session_repository.py -v`
Expected: ALL PASS

### Step 6: Commit

```bash
git add src/aion2meter/io/session_repository.py src/aion2meter/io/__init__.py tests/test_session_repository.py
git commit -m "feat(F1): SQLite 세션 저장소 구현"
```

---

## Task F2: 로깅 시스템

**Files:**
- Create: `src/aion2meter/logging_config.py`
- Modify: `src/aion2meter/app.py:1-5` (import 추가)
- Modify: `src/aion2meter/app.py:27` (setup_logging 호출)
- Modify: `src/aion2meter/pipeline/pipeline.py:38-39` (로깅 추가)
- Modify: `src/aion2meter/calculator/dps_calculator.py:34` (리셋 로깅)

### Step 1: Create logging_config.py

```python
# src/aion2meter/logging_config.py
"""로깅 설정."""

from __future__ import annotations

import logging
from pathlib import Path

_LOG_DIR = Path.home() / ".aion2meter" / "logs"


def setup_logging(level: int = logging.INFO) -> None:
    """파일 + 콘솔 로깅을 설정한다."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(_LOG_DIR / "aion2meter.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
```

### Step 2: Add logging to app.py

In `src/aion2meter/app.py`, add import at top (after line 7):
```python
from aion2meter.logging_config import setup_logging
```

In `App.__init__` (after line 28, before config load):
```python
        setup_logging()
```

### Step 3: Add logging to pipeline.py

In `src/aion2meter/pipeline/pipeline.py`, add at top (after line 6):
```python
import logging

logger = logging.getLogger(__name__)
```

In `CaptureWorker.run()`, replace `except Exception: pass` (line 38-39) with:
```python
            except Exception:
                logger.warning("캡처 실패", exc_info=True)
```

In `OcrWorker.enqueue()`, after the final `except queue.Full: pass` (line 84-85):
```python
            except queue.Full:
                logger.debug("프레임 큐 오버플로우")
```

### Step 4: Add logging to dps_calculator.py

In `src/aion2meter/calculator/dps_calculator.py`, add at top (after line 4):
```python
import logging

logger = logging.getLogger(__name__)
```

In `_reset_state()` (line 78), add at the beginning:
```python
        logger.info("전투 리셋")
```

### Step 5: Verify import works

Run: `PYTHONPATH=src python3 -c "from aion2meter.logging_config import setup_logging; setup_logging(); print('OK')"`
Expected: `OK`

### Step 6: Commit

```bash
git add src/aion2meter/logging_config.py src/aion2meter/app.py src/aion2meter/pipeline/pipeline.py src/aion2meter/calculator/dps_calculator.py
git commit -m "feat(F2): logging 모듈 통합"
```

---

## Task F3: 세션 리포트 UI + matplotlib 차트

**Files:**
- Modify: `pyproject.toml` (matplotlib 의존성 추가)
- Create: `src/aion2meter/ui/session_report.py`

### Step 1: Add matplotlib dependency

In `pyproject.toml`, add to `dependencies` list (line 14):
```toml
    "matplotlib>=3.8",
```

### Step 2: Create session_report.py

```python
# src/aion2meter/ui/session_report.py
"""세션 리포트 다이얼로그."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from aion2meter.io.session_repository import SessionRepository


class SessionListDialog(QDialog):
    """세션 목록 다이얼로그."""

    def __init__(self, repo: SessionRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("세션 기록")
        self.setMinimumSize(600, 400)
        self._repo = repo

        layout = QVBoxLayout(self)

        # 테이블
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["날짜/시간", "지속시간", "총 대미지", "평균 DPS", "Peak DPS"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table)

        # 버튼
        btn_row = QHBoxLayout()
        detail_btn = QPushButton("상세 보기")
        detail_btn.clicked.connect(self._open_detail)
        compare_btn = QPushButton("비교")
        compare_btn.clicked.connect(self._open_compare)
        delete_btn = QPushButton("삭제")
        delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(detail_btn)
        btn_row.addWidget(compare_btn)
        btn_row.addWidget(delete_btn)
        layout.addLayout(btn_row)

        self._session_ids: list[int] = []
        self._refresh()

    def _refresh(self) -> None:
        sessions = self._repo.list_sessions()
        self._session_ids = [s["id"] for s in sessions]
        self._table.setRowCount(len(sessions))
        for i, s in enumerate(sessions):
            dt = datetime.fromtimestamp(s["start_time"]).strftime("%Y-%m-%d %H:%M:%S") if s["start_time"] else "-"
            self._table.setItem(i, 0, QTableWidgetItem(dt))
            self._table.setItem(i, 1, QTableWidgetItem(f"{s['duration']:.1f}s"))
            self._table.setItem(i, 2, QTableWidgetItem(f"{s['total_damage']:,}"))
            self._table.setItem(i, 3, QTableWidgetItem(f"{s['avg_dps']:,.0f}"))
            self._table.setItem(i, 4, QTableWidgetItem(f"{s['peak_dps']:,.0f}"))

    def _selected_ids(self) -> list[int]:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        return [self._session_ids[r] for r in rows if r < len(self._session_ids)]

    def _on_double_click(self) -> None:
        self._open_detail()

    def _open_detail(self) -> None:
        ids = self._selected_ids()
        if ids:
            dlg = SessionDetailDialog(self._repo, ids[0], parent=self)
            dlg.exec()

    def _open_compare(self) -> None:
        ids = self._selected_ids()
        if len(ids) >= 2:
            from aion2meter.ui.session_compare import SessionCompareDialog
            dlg = SessionCompareDialog(self._repo, ids[0], ids[1], parent=self)
            dlg.exec()

    def _delete_selected(self) -> None:
        for sid in self._selected_ids():
            self._repo.delete_session(sid)
        self._refresh()


class SessionDetailDialog(QDialog):
    """세션 상세 리포트 다이얼로그."""

    def __init__(self, repo: SessionRepository, session_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"세션 #{session_id} 상세")
        self.setMinimumSize(700, 500)

        session = repo.get_session(session_id)
        skill_summary = repo.get_skill_summary(session_id)

        layout = QVBoxLayout(self)

        # 요약
        if session:
            dt = datetime.fromtimestamp(session["start_time"]).strftime("%Y-%m-%d %H:%M:%S")
            summary = (
                f"시간: {dt}  |  지속: {session['duration']:.1f}s  |  "
                f"총 대미지: {session['total_damage']:,}  |  "
                f"DPS: {session['avg_dps']:,.0f}  |  Peak: {session['peak_dps']:,.0f}"
            )
            lbl = QLabel(summary)
            lbl.setStyleSheet("font-size: 12px; padding: 8px;")
            layout.addWidget(lbl)

        # 차트 영역
        chart_row = QHBoxLayout()

        if skill_summary:
            names = [s["skill"] for s in skill_summary[:10]]
            damages = [s["total_damage"] for s in skill_summary[:10]]
            total = sum(damages) or 1

            # 바차트
            bar_canvas = SkillBarChart(names, damages)
            chart_row.addWidget(bar_canvas)

            # 파이차트
            pie_canvas = SkillPieChart(names, [d / total * 100 for d in damages])
            chart_row.addWidget(pie_canvas)

        layout.addLayout(chart_row)

        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class SkillBarChart(FigureCanvasQTAgg):
    """스킬별 대미지 수평 바차트."""

    def __init__(self, names: list[str], damages: list[int]) -> None:
        fig = Figure(figsize=(5, 3), facecolor="#1a1a1a")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#1a1a1a")

        y_pos = range(len(names))
        ax.barh(y_pos, damages, color="#00FF64", height=0.6)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(names, color="white", fontsize=9)
        ax.tick_params(axis="x", colors="white")
        ax.set_xlabel("대미지", color="white")
        ax.invert_yaxis()

        for spine in ax.spines.values():
            spine.set_color("#333333")

        fig.tight_layout()
        super().__init__(fig)


class SkillPieChart(FigureCanvasQTAgg):
    """스킬별 비율 파이차트."""

    def __init__(self, names: list[str], percentages: list[float]) -> None:
        fig = Figure(figsize=(4, 3), facecolor="#1a1a1a")
        ax = fig.add_subplot(111)

        colors = ["#00FF64", "#FFD700", "#FF6B6B", "#64B5F6", "#BA68C8",
                  "#4DB6AC", "#FF8A65", "#A1887F", "#90A4AE", "#E0E0E0"]
        ax.pie(
            percentages, labels=names, autopct="%.1f%%",
            colors=colors[:len(names)],
            textprops={"color": "white", "fontsize": 8},
        )
        fig.tight_layout()
        super().__init__(fig)
```

### Step 3: Verify import

Run: `PYTHONPATH=src python3 -c "from aion2meter.io.session_repository import SessionRepository; print('OK')"`
Expected: `OK`

### Step 4: Commit

```bash
git add pyproject.toml src/aion2meter/ui/session_report.py
git commit -m "feat(F3): 세션 리포트 UI + matplotlib 차트"
```

---

## Task F4: 세션 비교

**Files:**
- Create: `src/aion2meter/ui/session_compare.py`

### Step 1: Create session_compare.py

```python
# src/aion2meter/ui/session_compare.py
"""세션 비교 다이얼로그."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from aion2meter.io.session_repository import SessionRepository


class SessionCompareDialog(QDialog):
    """두 세션을 나란히 비교한다."""

    def __init__(
        self,
        repo: SessionRepository,
        id_a: int,
        id_b: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"세션 비교: #{id_a} vs #{id_b}")
        self.setMinimumSize(800, 500)

        session_a = repo.get_session(id_a)
        session_b = repo.get_session(id_b)
        skills_a = repo.get_skill_summary(id_a)
        skills_b = repo.get_skill_summary(id_b)

        layout = QVBoxLayout(self)

        # 요약 비교
        if session_a and session_b:
            dps_diff = session_b["avg_dps"] - session_a["avg_dps"]
            dps_pct = (dps_diff / session_a["avg_dps"] * 100) if session_a["avg_dps"] else 0
            sign = "+" if dps_diff >= 0 else ""

            dt_a = datetime.fromtimestamp(session_a["start_time"]).strftime("%m/%d %H:%M")
            dt_b = datetime.fromtimestamp(session_b["start_time"]).strftime("%m/%d %H:%M")

            summary = (
                f"A ({dt_a}): DPS {session_a['avg_dps']:,.0f}  |  "
                f"B ({dt_b}): DPS {session_b['avg_dps']:,.0f}  |  "
                f"차이: {sign}{dps_diff:,.0f} ({sign}{dps_pct:.1f}%)"
            )
            lbl = QLabel(summary)
            lbl.setStyleSheet("font-size: 12px; padding: 8px;")
            layout.addWidget(lbl)

        # 나란히 바차트
        if skills_a or skills_b:
            canvas = CompareBarChart(skills_a, skills_b)
            layout.addWidget(canvas)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class CompareBarChart(FigureCanvasQTAgg):
    """두 세션 스킬 대미지를 나란히 비교하는 차트."""

    def __init__(self, skills_a: list[dict], skills_b: list[dict]) -> None:
        fig = Figure(figsize=(8, 4), facecolor="#1a1a1a")

        ax1 = fig.add_subplot(121)
        ax2 = fig.add_subplot(122)

        for ax, skills, title, color in [
            (ax1, skills_a, "세션 A", "#00FF64"),
            (ax2, skills_b, "세션 B", "#FFD700"),
        ]:
            ax.set_facecolor("#1a1a1a")
            ax.set_title(title, color="white", fontsize=11)
            if skills:
                names = [s["skill"] for s in skills[:8]]
                damages = [s["total_damage"] for s in skills[:8]]
                y_pos = range(len(names))
                ax.barh(y_pos, damages, color=color, height=0.6)
                ax.set_yticks(y_pos)
                ax.set_yticklabels(names, color="white", fontsize=8)
                ax.invert_yaxis()
            ax.tick_params(axis="x", colors="white")
            for spine in ax.spines.values():
                spine.set_color("#333333")

        fig.tight_layout()
        super().__init__(fig)
```

### Step 2: Commit

```bash
git add src/aion2meter/ui/session_compare.py
git commit -m "feat(F4): 세션 비교 다이얼로그"
```

---

## Task F5: 앱 통합

**Files:**
- Modify: `src/aion2meter/ui/tray_icon.py:30-36` (시그널 추가)
- Modify: `src/aion2meter/ui/tray_icon.py:56-63` (메뉴 추가)
- Modify: `src/aion2meter/app.py` (세션 저장소 + 자동 저장 + 메뉴 연결)
- Modify: `src/aion2meter/calculator/dps_calculator.py` (리셋 콜백)
- Modify: `src/aion2meter/pipeline/pipeline.py` (리셋 전 스냅샷 반환)

### Step 1: Add on_combat_reset callback to DpsCalculator

In `src/aion2meter/calculator/dps_calculator.py`, add to `__init__` (after line 24):
```python
        self._on_reset_callback: callable | None = None
```

Add method (after `get_event_history`):
```python
    def set_on_reset(self, callback: callable) -> None:
        """자동/수동 리셋 시 호출될 콜백을 설정한다. callback(events, snapshot)."""
        self._on_reset_callback = callback
```

In `_reset_state()`, before clearing state (at line 78):
```python
        # 콜백 호출 (히스토리가 남아 있을 때)
        if self._on_reset_callback and self._event_history:
            snapshot = DpsSnapshot(
                dps=self._total_damage / max(self._calc_elapsed(), 0.001) if self._total_damage > 0 else 0.0,
                total_damage=self._total_damage,
                elapsed_seconds=self._calc_elapsed(),
                peak_dps=self._peak_dps,
                combat_active=False,
                skill_breakdown=dict(self._skill_breakdown),
                event_count=self._event_count,
            )
            self._on_reset_callback(list(self._event_history), snapshot)
```

### Step 2: Add signals to TrayIcon

In `src/aion2meter/ui/tray_icon.py`, add signals (after line 36):
```python
    open_sessions = pyqtSignal()
    open_compare = pyqtSignal()
```

Add menu items in `__init__` (before the separator at line 64):
```python
        sessions_action = QAction("세션 기록", menu)
        sessions_action.triggered.connect(self.open_sessions.emit)
        menu.addAction(sessions_action)
```

### Step 3: Update app.py

Add imports at top:
```python
from aion2meter.io.session_repository import SessionRepository
from aion2meter.logging_config import setup_logging
from aion2meter.ui.session_report import SessionListDialog
```

In `App.__init__`, add after config load:
```python
        setup_logging()
        self._session_repo = SessionRepository()
```

Set reset callback after pipeline creation:
```python
        self._pipeline._calculator.set_on_reset(self._on_combat_ended)
```

Connect new tray signals:
```python
        self._tray.open_sessions.connect(self._open_sessions)
```

Add methods:
```python
    def _on_combat_ended(self, events: list, snapshot) -> None:
        """전투 종료(자동/수동 리셋) 시 세션을 저장한다."""
        if events:
            self._session_repo.save_session(events, snapshot)

    def _open_sessions(self) -> None:
        dlg = SessionListDialog(self._session_repo)
        dlg.exec()
```

In `_quit`, add before pipeline stop:
```python
        # 활성 세션 저장
        events = self._pipeline.get_event_history()
        if events:
            snapshot = self._pipeline._calculator.add_events([])  # 현재 스냅샷
            self._session_repo.save_session(events, snapshot)
```

### Step 4: Run all tests

Run: `python3 -m pytest tests/test_config.py tests/test_calculator.py tests/test_combat_logger.py tests/test_session_repository.py tests/test_models.py tests/test_parser.py tests/test_ocr.py -v`
Expected: ALL PASS

### Step 5: Commit

```bash
git add src/aion2meter/calculator/dps_calculator.py src/aion2meter/ui/tray_icon.py src/aion2meter/app.py
git commit -m "feat(F5): 앱 통합 - 세션 자동 저장, 트레이 메뉴 연결"
```

---

## Task F6: PyInstaller 빌드

**Files:**
- Modify: `pyproject.toml` (build 의존성)
- Create: `scripts/build.py`
- Create: `aion2meter.spec`

### Step 1: Update pyproject.toml

Add to `[project.optional-dependencies]`:
```toml
build = ["pyinstaller>=6.0"]
```

### Step 2: Create build script

```python
# scripts/build.py
"""PyInstaller 빌드 스크립트."""

import subprocess
import sys

def main() -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "aion2meter",
        "--hidden-import", "winocr",
        "--hidden-import", "pytesseract",
        "--hidden-import", "matplotlib.backends.backend_qtagg",
        "src/aion2meter/__main__.py",
    ]
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    main()
```

### Step 3: Create spec file

```python
# aion2meter.spec
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['src/aion2meter/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'winocr',
        'pytesseract',
        'matplotlib.backends.backend_qtagg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='aion2meter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)
```

### Step 4: Commit

```bash
git add pyproject.toml scripts/build.py aion2meter.spec
git commit -m "feat(F6): PyInstaller 빌드 설정"
```

---

## 실행 순서 요약

```
F1 (SQLite) + F2 (로깅)    ← 병렬 실행 가능
    ↓
F3 (리포트 UI + 차트)
    ↓
F4 (세션 비교)
    ↓
F5 (앱 통합)
    ↓
F6 (PyInstaller)
```

## 최종 검증

```bash
# 전체 테스트
python3 -m pytest tests/ -v --ignore=tests/test_capture.py --ignore=tests/test_pipeline.py --ignore=tests/test_preprocess.py

# import 검증
PYTHONPATH=src python3 -c "from aion2meter.io.session_repository import SessionRepository; from aion2meter.logging_config import setup_logging; print('OK')"
```
