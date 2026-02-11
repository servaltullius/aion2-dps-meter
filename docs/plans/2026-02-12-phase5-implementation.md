# Phase 5: 타임라인 + 단축키 + 자동 업데이트 + 최적화 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** DPS 타임라인 차트, 글로벌 키보드 단축키, GitHub 자동 업데이트, 성능 최적화를 추가한다.

**Architecture:** DpsCalculator가 시계열 DPS를 추적하여 DpsSnapshot에 포함하고, 오버레이는 QPainter 스파크라인으로 실시간 표시한다. pynput으로 글로벌 핫키를 처리하고, urllib로 GitHub Releases를 확인한다. 중복 프레임 감지를 픽셀 샘플링으로 교체하여 CPU를 줄인다.

**Tech Stack:** PyQt6, matplotlib, pynput, urllib.request, collections.deque

---

## Task G1: DPS 타임라인 데이터 모델 + 저장소

**Files:**
- Modify: `src/aion2meter/models.py:79-89`
- Modify: `src/aion2meter/calculator/dps_calculator.py`
- Modify: `src/aion2meter/io/session_repository.py`
- Test: `tests/test_calculator.py`
- Test: `tests/test_session_repository.py`

**Step 1: Write failing tests for timeline tracking**

`tests/test_calculator.py` 파일 끝에 추가:

```python
class TestDpsTimeline:
    """DPS 타임라인 추적."""

    def test_empty_timeline_initially(self):
        calc = RealtimeDpsCalculator()
        assert calc.get_dps_timeline() == []

    def test_timeline_grows_with_events(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([_make_event(timestamp=10.0, damage=1000)])
        calc.add_events([_make_event(timestamp=12.0, damage=2000)])
        timeline = calc.get_dps_timeline()
        assert len(timeline) == 2

    def test_timeline_contains_elapsed_and_dps(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([_make_event(timestamp=10.0, damage=1000)])
        calc.add_events([_make_event(timestamp=12.0, damage=2000)])
        timeline = calc.get_dps_timeline()
        # 첫 포인트: elapsed=0.0 (첫 이벤트)
        assert timeline[0][0] == pytest.approx(0.0)
        # 두 번째: elapsed=2.0
        assert timeline[1][0] == pytest.approx(2.0)
        # DPS 값이 양수
        assert timeline[0][1] > 0
        assert timeline[1][1] > 0

    def test_timeline_cleared_on_reset(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([_make_event(timestamp=1.0, damage=1000)])
        calc.reset()
        assert calc.get_dps_timeline() == []

    def test_timeline_cleared_on_auto_reset(self):
        calc = RealtimeDpsCalculator(idle_timeout=5.0)
        calc.add_events([_make_event(timestamp=1.0, damage=1000)])
        calc.add_events([_make_event(timestamp=20.0, damage=500)])
        timeline = calc.get_dps_timeline()
        # 리셋 후 새 전투만 남아야 함
        assert len(timeline) == 1

    def test_snapshot_includes_recent_timeline(self):
        calc = RealtimeDpsCalculator()
        calc.add_events([_make_event(timestamp=10.0, damage=1000)])
        snap = calc.add_events([_make_event(timestamp=12.0, damage=2000)])
        assert len(snap.dps_timeline) == 2
        assert snap.dps_timeline[0][0] == pytest.approx(0.0)
        assert snap.dps_timeline[1][0] == pytest.approx(2.0)

    def test_snapshot_timeline_capped_at_120(self):
        calc = RealtimeDpsCalculator()
        for i in range(150):
            calc.add_events([_make_event(timestamp=float(i), damage=100)])
        snap = calc.add_events([_make_event(timestamp=200.0, damage=100)])
        # 전체는 151이지만 스냅샷은 최근 120개만
        assert len(snap.dps_timeline) <= 120
        assert len(calc.get_dps_timeline()) == 151
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_calculator.py::TestDpsTimeline -v`
Expected: FAIL — `get_dps_timeline` 미존재 또는 `dps_timeline` 필드 없음

**Step 3: Implement DpsSnapshot.dps_timeline field**

`src/aion2meter/models.py` — DpsSnapshot에 필드 추가:

```python
@dataclass(frozen=True)
class DpsSnapshot:
    """특정 시점의 DPS 스냅샷."""

    dps: float
    total_damage: int
    elapsed_seconds: float
    peak_dps: float
    combat_active: bool
    skill_breakdown: dict[str, int] = field(default_factory=dict)
    event_count: int = 0
    dps_timeline: list[tuple[float, float]] = field(default_factory=list)
```

**Step 4: Implement timeline tracking in Calculator**

`src/aion2meter/calculator/dps_calculator.py` — 전체 교체:

```python
"""실시간 DPS 계산 엔진."""

from __future__ import annotations

from aion2meter.models import DamageEvent, DpsSnapshot

import logging
logger = logging.getLogger(__name__)

_MAX_TIMELINE_IN_SNAPSHOT = 120


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
        self._dps_timeline: list[tuple[float, float]] = []
        self._on_reset_callback: object | None = None

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

            # 타임라인 기록
            elapsed = self._calc_elapsed()
            dps = self._total_damage / max(elapsed, 0.001)
            self._dps_timeline.append((elapsed, dps))

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
            dps_timeline=list(self._dps_timeline[-_MAX_TIMELINE_IN_SNAPSHOT:]),
        )

    def get_event_history(self) -> list[DamageEvent]:
        """현재 전투의 이벤트 히스토리를 반환한다."""
        return list(self._event_history)

    def get_dps_timeline(self) -> list[tuple[float, float]]:
        """현재 전투의 전체 DPS 타임라인을 반환한다."""
        return list(self._dps_timeline)

    def set_on_reset(self, callback: object) -> None:
        """자동/수동 리셋 시 호출될 콜백을 설정한다. callback(events, snapshot)."""
        self._on_reset_callback = callback

    def reset(self) -> None:
        """모든 상태를 초기화한다."""
        self._reset_state()

    def _reset_state(self) -> None:
        """내부 상태를 초기화한다."""
        if self._on_reset_callback and self._event_history:
            snapshot = DpsSnapshot(
                dps=self._total_damage / max(self._calc_elapsed(), 0.001) if self._total_damage > 0 else 0.0,
                total_damage=self._total_damage,
                elapsed_seconds=self._calc_elapsed(),
                peak_dps=self._peak_dps,
                combat_active=False,
                skill_breakdown=dict(self._skill_breakdown),
                event_count=self._event_count,
                dps_timeline=list(self._dps_timeline),
            )
            self._on_reset_callback(list(self._event_history), snapshot)
        logger.info("전투 리셋")
        self._total_damage = 0
        self._event_count = 0
        self._peak_dps = 0.0
        self._skill_breakdown = {}
        self._first_timestamp = None
        self._last_timestamp = None
        self._event_history = []
        self._dps_timeline = []

    def _calc_elapsed(self) -> float:
        """경과 시간(초)을 계산한다."""
        if self._first_timestamp is None or self._last_timestamp is None:
            return 0.0
        return self._last_timestamp - self._first_timestamp
```

**Step 5: Run calculator tests**

Run: `pytest tests/test_calculator.py -v`
Expected: ALL PASS

**Step 6: Write failing tests for timeline in SessionRepository**

`tests/test_session_repository.py` 파일 끝에 추가:

```python
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
```

**Step 7: Run to verify they fail**

Run: `pytest tests/test_session_repository.py::TestSessionTimeline -v`
Expected: FAIL — `get_session_timeline` 미존재

**Step 8: Implement session_timeline in SessionRepository**

`src/aion2meter/io/session_repository.py` — `_SCHEMA`에 테이블 추가, `save_session`에 타임라인 삽입, `get_session_timeline` 메서드 추가.

`_SCHEMA` 문자열 끝에 추가:
```sql
CREATE TABLE IF NOT EXISTS session_timeline (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    elapsed     REAL NOT NULL,
    dps         REAL NOT NULL
);
```

`save_session` 메서드 — `self._conn.commit()` 직전에 추가:
```python
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
```

새 메서드 추가 (`delete_session` 아래):
```python
    def get_session_timeline(self, session_id: int) -> list[dict]:
        """세션의 DPS 타임라인을 시간순으로 반환한다."""
        cur = self._conn.execute(
            "SELECT * FROM session_timeline "
            "WHERE session_id = ? ORDER BY elapsed",
            (session_id,),
        )
        return [dict(row) for row in cur.fetchall()]
```

**Step 9: Run all repository tests**

Run: `pytest tests/test_session_repository.py -v`
Expected: ALL PASS

**Step 10: Run full test suite**

Run: `pytest tests/test_calculator.py tests/test_session_repository.py tests/test_models.py tests/test_config.py tests/test_combat_logger.py tests/test_parser.py -v`
Expected: ALL PASS

---

## Task G4: 키보드 단축키

**Files:**
- Modify: `src/aion2meter/models.py:92-106`
- Modify: `src/aion2meter/config.py`
- Create: `src/aion2meter/hotkey_manager.py`
- Test: `tests/test_hotkey_manager.py`
- Test: `tests/test_config.py`

**Step 1: Add hotkey fields to AppConfig**

`src/aion2meter/models.py` — `AppConfig`에 필드 추가 (`color_ranges` 위에):
```python
    hotkey_overlay: str = "<ctrl>+<shift>+o"
    hotkey_reset: str = "<ctrl>+<shift>+r"
    hotkey_breakdown: str = "<ctrl>+<shift>+b"
```

**Step 2: Write failing config tests**

`tests/test_config.py` 파일 끝에 추가:
```python
class TestHotkeyConfig:
    """핫키 설정 직렬화/역직렬화."""

    def test_default_hotkeys(self):
        config = AppConfig()
        assert config.hotkey_overlay == "<ctrl>+<shift>+o"
        assert config.hotkey_reset == "<ctrl>+<shift>+r"
        assert config.hotkey_breakdown == "<ctrl>+<shift>+b"

    def test_hotkey_roundtrip(self, tmp_path):
        config = AppConfig(
            hotkey_overlay="<ctrl>+<alt>+d",
            hotkey_reset="<ctrl>+<alt>+r",
            hotkey_breakdown="<ctrl>+<alt>+b",
        )
        mgr = ConfigManager(default_path=tmp_path / "config.toml")
        mgr.save(config)
        loaded = mgr.load()
        assert loaded.hotkey_overlay == "<ctrl>+<alt>+d"
        assert loaded.hotkey_reset == "<ctrl>+<alt>+r"
        assert loaded.hotkey_breakdown == "<ctrl>+<alt>+b"
```

**Step 3: Run to verify they fail**

Run: `pytest tests/test_config.py::TestHotkeyConfig -v`
Expected: FAIL — `hotkey_overlay` 필드 없음 또는 직렬화 누락

**Step 4: Update ConfigManager for hotkeys**

`src/aion2meter/config.py` — `_serialize()`에 추가 (overlay_bg_color 줄 다음):
```python
        lines.append(f'hotkey_overlay = "{config.hotkey_overlay}"')
        lines.append(f'hotkey_reset = "{config.hotkey_reset}"')
        lines.append(f'hotkey_breakdown = "{config.hotkey_breakdown}"')
```

`load()`에 추가 (return 문의 AppConfig 생성자에):
```python
            hotkey_overlay=str(data.get("hotkey_overlay", "<ctrl>+<shift>+o")),
            hotkey_reset=str(data.get("hotkey_reset", "<ctrl>+<shift>+r")),
            hotkey_breakdown=str(data.get("hotkey_breakdown", "<ctrl>+<shift>+b")),
```

**Step 5: Run config tests**

Run: `pytest tests/test_config.py -v`
Expected: ALL PASS

**Step 6: Write failing HotkeyManager tests**

Create `tests/test_hotkey_manager.py`:
```python
"""HotkeyManager 단위 테스트."""

from __future__ import annotations

from aion2meter.hotkey_manager import HotkeyManager


class TestHotkeyManager:
    """HotkeyManager 기본 동작."""

    def test_create_instance(self):
        mgr = HotkeyManager()
        assert mgr is not None

    def test_register_and_unregister(self):
        mgr = HotkeyManager()
        called = []
        mgr.register("<ctrl>+<shift>+t", lambda: called.append(1))
        mgr.unregister_all()
        # unregister 후 hotkeys 비어있어야 함
        assert mgr._hotkeys == {}

    def test_register_multiple(self):
        mgr = HotkeyManager()
        mgr.register("<ctrl>+<shift>+a", lambda: None)
        mgr.register("<ctrl>+<shift>+b", lambda: None)
        assert len(mgr._hotkeys) == 2

    def test_register_overwrites_same_key(self):
        mgr = HotkeyManager()
        mgr.register("<ctrl>+<shift>+a", lambda: None)
        mgr.register("<ctrl>+<shift>+a", lambda: None)
        assert len(mgr._hotkeys) == 1

    def test_empty_hotkey_string_ignored(self):
        mgr = HotkeyManager()
        mgr.register("", lambda: None)
        assert mgr._hotkeys == {}

    def test_stop_without_start(self):
        mgr = HotkeyManager()
        mgr.stop()  # 에러 없이 통과해야 함
```

**Step 7: Run to verify they fail**

Run: `pytest tests/test_hotkey_manager.py -v`
Expected: FAIL — `aion2meter.hotkey_manager` 모듈 없음

**Step 8: Implement HotkeyManager**

Create `src/aion2meter/hotkey_manager.py`:
```python
"""글로벌 키보드 단축키 관리자."""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


class HotkeyManager:
    """pynput 기반 글로벌 핫키 관리자.

    pynput이 설치되지 않은 환경에서도 에러 없이 동작한다 (기능 비활성).
    """

    def __init__(self) -> None:
        self._hotkeys: dict[str, Callable] = {}
        self._listener: object | None = None

    def register(self, hotkey: str, callback: Callable) -> None:
        """핫키를 등록한다. 빈 문자열은 무시."""
        if not hotkey:
            return
        self._hotkeys[hotkey] = callback

    def unregister_all(self) -> None:
        """모든 핫키를 해제한다."""
        self._hotkeys = {}

    def start(self) -> None:
        """핫키 리스너를 시작한다."""
        if not self._hotkeys:
            return
        try:
            from pynput.keyboard import GlobalHotKeys
            self._listener = GlobalHotKeys(self._hotkeys)
            self._listener.start()
            logger.info("핫키 리스너 시작: %s", list(self._hotkeys.keys()))
        except ImportError:
            logger.warning("pynput 미설치 — 단축키 비활성")
        except Exception:
            logger.warning("핫키 리스너 시작 실패", exc_info=True)

    def stop(self) -> None:
        """핫키 리스너를 종료한다."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
```

**Step 9: Run hotkey tests**

Run: `pytest tests/test_hotkey_manager.py -v`
Expected: ALL PASS

---

## Task G5: 자동 업데이트 확인

**Files:**
- Modify: `src/aion2meter/models.py:92-106`
- Modify: `src/aion2meter/config.py`
- Create: `src/aion2meter/updater.py`
- Test: `tests/test_updater.py`

**Step 1: Add auto_update_check to AppConfig**

`src/aion2meter/models.py` — AppConfig에 필드 추가 (`hotkey_breakdown` 아래):
```python
    auto_update_check: bool = True
```

**Step 2: Update ConfigManager**

`src/aion2meter/config.py` — `_serialize()`에 추가 (hotkey_breakdown 줄 다음):
```python
        lines.append(f"auto_update_check = {'true' if config.auto_update_check else 'false'}")
```

`load()`에 추가:
```python
            auto_update_check=bool(data.get("auto_update_check", True)),
```

**Step 3: Write failing updater tests**

Create `tests/test_updater.py`:
```python
"""자동 업데이트 확인 단위 테스트."""

from __future__ import annotations

import json

import pytest

from aion2meter.updater import compare_versions, parse_release_info


class TestVersionCompare:
    """버전 비교 로직."""

    def test_newer_version(self):
        assert compare_versions("0.1.0", "0.2.0") is True

    def test_same_version(self):
        assert compare_versions("0.1.0", "0.1.0") is False

    def test_older_version(self):
        assert compare_versions("0.2.0", "0.1.0") is False

    def test_patch_version(self):
        assert compare_versions("0.1.0", "0.1.1") is True

    def test_major_version(self):
        assert compare_versions("0.9.9", "1.0.0") is True

    def test_with_v_prefix(self):
        assert compare_versions("0.1.0", "v0.2.0") is True

    def test_both_v_prefix(self):
        assert compare_versions("v0.1.0", "v0.1.0") is False


class TestParseReleaseInfo:
    """GitHub API 응답 파싱."""

    def test_parse_valid_response(self):
        data = json.dumps({
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/servaltullius/aion2-dps-meter/releases/tag/v0.2.0",
            "assets": [
                {
                    "name": "aion2meter.exe",
                    "browser_download_url": "https://example.com/aion2meter.exe",
                }
            ],
        })
        version, url = parse_release_info(data)
        assert version == "0.2.0"
        assert "aion2meter" in url

    def test_parse_no_assets(self):
        data = json.dumps({
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/servaltullius/aion2-dps-meter/releases/tag/v0.2.0",
            "assets": [],
        })
        version, url = parse_release_info(data)
        assert version == "0.2.0"
        # 에셋 없으면 릴리스 페이지 URL
        assert "releases" in url

    def test_parse_invalid_json(self):
        with pytest.raises(ValueError):
            parse_release_info("not json")
```

**Step 4: Run to verify they fail**

Run: `pytest tests/test_updater.py -v`
Expected: FAIL — `aion2meter.updater` 모듈 없음

**Step 5: Implement updater module**

Create `src/aion2meter/updater.py`:
```python
"""GitHub Releases 기반 자동 업데이트 확인."""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_RELEASES_URL = (
    "https://api.github.com/repos/servaltullius/aion2-dps-meter/releases/latest"
)


def compare_versions(current: str, latest: str) -> bool:
    """latest가 current보다 새 버전이면 True를 반환한다."""
    def _normalize(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.lstrip("v").split("."))

    return _normalize(latest) > _normalize(current)


def parse_release_info(raw_json: str) -> tuple[str, str]:
    """GitHub API JSON에서 (version, download_url)을 추출한다.

    Raises:
        ValueError: JSON 파싱 실패
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}") from e

    tag = data["tag_name"]
    version = tag.lstrip("v")

    # 에셋 중 exe 파일 우선, 없으면 릴리스 페이지 URL
    assets = data.get("assets", [])
    download_url = data.get("html_url", "")
    for asset in assets:
        if asset["name"].endswith(".exe"):
            download_url = asset["browser_download_url"]
            break

    return version, download_url


def check_for_update(current_version: str) -> tuple[str, str] | None:
    """GitHub에서 최신 릴리스를 확인한다.

    Returns:
        (latest_version, download_url) 또는 None (업데이트 없거나 실패)
    """
    try:
        req = urllib.request.Request(
            _RELEASES_URL,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")

        version, url = parse_release_info(raw)
        if compare_versions(current_version, version):
            return version, url
        return None
    except Exception:
        logger.debug("업데이트 확인 실패", exc_info=True)
        return None
```

**Step 6: Run updater tests**

Run: `pytest tests/test_updater.py -v`
Expected: ALL PASS

**Step 7: Run config tests (auto_update_check 확인)**

Run: `pytest tests/test_config.py -v`
Expected: ALL PASS

---

## Task G6: 성능 최적화

**Files:**
- Modify: `src/aion2meter/preprocess/image_proc.py:49-56`
- Modify: `src/aion2meter/calculator/dps_calculator.py`
- Modify: `src/aion2meter/pipeline/pipeline.py:76-88`
- Test: `tests/test_calculator.py`

**Step 1: Write failing test for bounded event history**

`tests/test_calculator.py` 파일 끝에 추가:
```python
class TestBoundedEventHistory:
    """이벤트 히스토리 최대 크기 제한."""

    def test_history_capped_at_max(self):
        calc = RealtimeDpsCalculator()
        events = [_make_event(timestamp=float(i), damage=10) for i in range(12000)]
        calc.add_events(events)
        history = calc.get_event_history()
        assert len(history) <= 10000

    def test_history_keeps_recent_events(self):
        calc = RealtimeDpsCalculator()
        events = [_make_event(timestamp=float(i), damage=i + 1) for i in range(12000)]
        calc.add_events(events)
        history = calc.get_event_history()
        # 가장 마지막 이벤트가 보존되어야 함
        assert history[-1].damage == 12000
```

**Step 2: Run to verify they fail**

Run: `pytest tests/test_calculator.py::TestBoundedEventHistory -v`
Expected: FAIL — `len(history) > 10000`

**Step 3: Replace list with deque in Calculator**

`src/aion2meter/calculator/dps_calculator.py` — import 추가 및 변경:

상단에 `from collections import deque` 추가.

`__init__`에서:
```python
        self._event_history: deque[DamageEvent] = deque(maxlen=10000)
```

`get_event_history` 반환:
```python
        return list(self._event_history)
```

`_reset_state`에서:
```python
        self._event_history = deque(maxlen=10000)
```

**Step 4: Run bounded history tests**

Run: `pytest tests/test_calculator.py -v`
Expected: ALL PASS

**Step 5: Optimize duplicate frame detection**

`src/aion2meter/preprocess/image_proc.py` — `is_duplicate` 메서드 교체:

```python
    def is_duplicate(self, frame: CapturedFrame) -> bool:
        """이전 프레임과 동일한지 5지점 픽셀 샘플링으로 비교한다."""
        image: np.ndarray = frame.image  # type: ignore[assignment]
        h, w = image.shape[:2]
        if h == 0 or w == 0:
            return False

        # 5지점 샘플: 4모서리 + 중앙
        points = [
            (0, 0),
            (0, w - 1),
            (h - 1, 0),
            (h - 1, w - 1),
            (h // 2, w // 2),
        ]
        sample = tuple(image[y, x].tobytes() for y, x in points)

        if self._prev_hash is not None and sample == self._prev_hash:
            return True
        self._prev_hash = sample
        return False
```

`hashlib` import 제거 (더 이상 필요 없음).

**Step 6: Optimize frame skip in OcrWorker**

`src/aion2meter/pipeline/pipeline.py` — `OcrWorker.run()` 메서드에서 프레임 가져온 후:

```python
    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                frame = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # 큐에 더 있으면 최신만 처리 (stale 프레임 스킵)
            while not self._queue.empty():
                try:
                    frame = self._queue.get_nowait()
                except queue.Empty:
                    break

            if self._preprocessor.is_duplicate(frame):
                continue

            processed = self._preprocessor.process(frame)
            ocr_result = self._ocr_engine.recognize(processed)

            if not ocr_result.text.strip():
                continue

            events = self._parser.parse(ocr_result.text, frame.timestamp)
            if events:
                snapshot = self._calculator.add_events(events)
                self.dps_updated.emit(snapshot)
```

**Step 7: Run all tests**

Run: `pytest tests/test_calculator.py tests/test_session_repository.py tests/test_models.py tests/test_config.py tests/test_combat_logger.py tests/test_parser.py -v`
Expected: ALL PASS

---

## Task G2: 오버레이 스파크라인

**Files:**
- Create: `src/aion2meter/ui/sparkline.py`
- Modify: `src/aion2meter/ui/overlay.py`

> Note: UI 위젯이므로 자동화 테스트 없음. 수동 검증 필요.

**Step 1: Create SparklineWidget**

Create `src/aion2meter/ui/sparkline.py`:
```python
"""실시간 DPS 스파크라인 위젯."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

_LINE_COLOR = QColor(0, 255, 100)
_GRID_COLOR = QColor(255, 255, 255, 30)


class SparklineWidget(QWidget):
    """QPainter 기반 경량 스파크라인 차트."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(200, 40)
        self._data: list[tuple[float, float]] = []

    def update_data(self, timeline: list[tuple[float, float]]) -> None:
        """타임라인 데이터를 갱신한다. (elapsed, dps) 튜플 리스트."""
        self._data = timeline
        self.update()

    def paintEvent(self, event: object) -> None:
        if len(self._data) < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 2

        # 그리드 (수평 반선)
        painter.setPen(QPen(_GRID_COLOR, 1))
        painter.drawLine(margin, h // 2, w - margin, h // 2)

        # Y축 스케일
        max_dps = max(d for _, d in self._data)
        if max_dps <= 0:
            return

        # 라인 패스
        path = QPainterPath()
        data_w = w - 2 * margin
        data_h = h - 2 * margin
        n = len(self._data)

        for i, (_, dps) in enumerate(self._data):
            x = margin + (i / max(n - 1, 1)) * data_w
            y = margin + data_h - (dps / max_dps) * data_h
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        painter.setPen(QPen(_LINE_COLOR, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()
```

**Step 2: Integrate SparklineWidget into Overlay**

`src/aion2meter/ui/overlay.py` — 변경사항:

상단 import 추가:
```python
from aion2meter.ui.sparkline import SparklineWidget
```

상수 수정:
```python
_BREAKDOWN_HEIGHT = 140  # 스파크라인(40) + 스킬(100)
```

`__init__` 메서드 — skill_labels 루프 직전에 스파크라인 추가:
```python
        # 스파크라인
        self._sparkline = SparklineWidget(self)
        self._sparkline.setVisible(False)
        layout.addWidget(self._sparkline)
```

`update_display` 메서드 — skill breakdown 갱신 블록 직전에 추가:
```python
        # 스파크라인 갱신
        if self._breakdown_visible and snapshot.dps_timeline:
            self._sparkline.update_data(snapshot.dps_timeline)
            self._sparkline.setVisible(True)
        elif not self._breakdown_visible:
            self._sparkline.setVisible(False)
```

`toggle_breakdown` 메서드:
```python
    def toggle_breakdown(self) -> None:
        """스킬 breakdown + 스파크라인 표시/숨기기 토글."""
        self._breakdown_visible = not self._breakdown_visible
        if self._breakdown_visible:
            self.setFixedSize(_BASE_WIDTH, _BASE_HEIGHT + _BREAKDOWN_HEIGHT)
            self._sparkline.setVisible(True)
        else:
            for lbl in self._skill_labels:
                lbl.setVisible(False)
            self._sparkline.setVisible(False)
            self.setFixedSize(_BASE_WIDTH, _BASE_HEIGHT)
```

**Step 3: Verify import**

Run: `PYTHONPATH=src python3 -c "from aion2meter.ui.sparkline import SparklineWidget; print('OK')"`
Expected: `OK`

---

## Task G3: 세션 리포트 타임라인 차트

**Files:**
- Modify: `src/aion2meter/ui/session_report.py`

**Step 1: Add DpsTimelineChart class**

`src/aion2meter/ui/session_report.py` — `SkillPieChart` 클래스 뒤에 추가:

```python
class DpsTimelineChart(FigureCanvasQTAgg):
    """DPS 타임라인 라인 차트."""

    def __init__(
        self,
        times: list[float],
        dps_values: list[float],
        avg_dps: float = 0.0,
        peak_dps: float = 0.0,
    ) -> None:
        fig = Figure(figsize=(9, 2.5), tight_layout=True)
        fig.set_facecolor("#1a1a1a")
        super().__init__(fig)

        ax = fig.add_subplot(111)
        ax.set_facecolor("#1a1a1a")
        ax.plot(times, dps_values, color="#00FF64", linewidth=1.2)

        if peak_dps > 0:
            ax.axhline(y=peak_dps, color="#FF6B6B", linestyle="--", linewidth=0.8, label=f"Peak: {peak_dps:,.0f}")
        if avg_dps > 0:
            ax.axhline(y=avg_dps, color="#FFD700", linestyle="--", linewidth=0.8, label=f"Avg: {avg_dps:,.0f}")

        ax.set_xlabel("시간 (초)", color="white")
        ax.set_ylabel("DPS", color="white")
        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_color("#333333")
        if peak_dps > 0 or avg_dps > 0:
            ax.legend(loc="upper right", facecolor="#2a2a2a", edgecolor="#555555", labelcolor="white")
```

**Step 2: Integrate into SessionDetailDialog**

`src/aion2meter/ui/session_report.py` — `SessionDetailDialog.__init__` 수정.

summary 위젯 다음, skill_rows 조회 전에 타임라인 차트 추가:

```python
        # DPS 타임라인
        timeline_rows = repo.get_session_timeline(session_id)
        if timeline_rows:
            times = [r["elapsed"] for r in timeline_rows]
            dps_values = [r["dps"] for r in timeline_rows]
            timeline_chart = DpsTimelineChart(
                times, dps_values, avg_dps=avg_dps, peak_dps=peak_dps,
            )
            layout.addWidget(timeline_chart)
```

**Step 3: Verify import**

Run: `PYTHONPATH=src python3 -c "from aion2meter.ui.session_report import DpsTimelineChart; print('OK')"`
Expected: `OK`

---

## Task G7: 앱 통합

**Files:**
- Modify: `src/aion2meter/ui/tray_icon.py`
- Modify: `src/aion2meter/ui/settings_dialog.py`
- Modify: `src/aion2meter/app.py`
- Modify: `pyproject.toml`

**Step 1: Add pynput dependency**

`pyproject.toml` — dependencies에 추가:
```toml
    "pynput>=1.7",
```

**Step 2: Add "업데이트 확인" to TrayIcon**

`src/aion2meter/ui/tray_icon.py` — 시그널 추가:
```python
    check_update = pyqtSignal()
```

메뉴에 추가 (sessions_action 다음, separator 전):
```python
        update_action = QAction("업데이트 확인", menu)
        update_action.triggered.connect(self.check_update.emit)
        menu.addAction(update_action)
```

**Step 3: Extend SettingsDialog**

`src/aion2meter/ui/settings_dialog.py` — import 추가:
```python
from PyQt6.QtWidgets import (
    ...,
    QCheckBox,
    QLineEdit,
)
```

`__init__` 메서드 — 배경색 행 다음에 추가:
```python
        # 단축키 설정
        self._hotkey_overlay_edit = QLineEdit(config.hotkey_overlay)
        form.addRow("오버레이 단축키:", self._hotkey_overlay_edit)

        self._hotkey_reset_edit = QLineEdit(config.hotkey_reset)
        form.addRow("전투 초기화 단축키:", self._hotkey_reset_edit)

        self._hotkey_breakdown_edit = QLineEdit(config.hotkey_breakdown)
        form.addRow("스킬 상세 단축키:", self._hotkey_breakdown_edit)

        # 자동 업데이트
        self._auto_update_check = QCheckBox("자동 업데이트 확인")
        self._auto_update_check.setChecked(config.auto_update_check)
        form.addRow("", self._auto_update_check)
```

`_apply` 메서드에 추가:
```python
        self._config.hotkey_overlay = self._hotkey_overlay_edit.text()
        self._config.hotkey_reset = self._hotkey_reset_edit.text()
        self._config.hotkey_breakdown = self._hotkey_breakdown_edit.text()
        self._config.auto_update_check = self._auto_update_check.isChecked()
```

**Step 4: Wire everything in app.py**

`src/aion2meter/app.py` — import 추가:
```python
from aion2meter.hotkey_manager import HotkeyManager
from aion2meter.updater import check_for_update
```

`__init__` 메서드 — `self._tray.show()` 뒤에 추가:
```python
        # 글로벌 단축키
        self._hotkey_mgr = HotkeyManager()
        self._hotkey_mgr.register(self._config.hotkey_overlay, self._toggle_overlay)
        self._hotkey_mgr.register(self._config.hotkey_reset, self._reset_combat)
        self._hotkey_mgr.register(self._config.hotkey_breakdown, self._toggle_breakdown)
        self._hotkey_mgr.start()

        # 자동 업데이트 확인
        self._tray.check_update.connect(self._check_update)
        if self._config.auto_update_check:
            self._check_update()
```

새 메서드 추가:
```python
    def _check_update(self) -> None:
        """GitHub에서 최신 버전을 확인한다."""
        import threading

        def _check():
            result = check_for_update("0.1.0")
            if result:
                version, url = result
                self._tray.showMessage(
                    "업데이트 알림",
                    f"새 버전 {version}이 있습니다.\n{url}",
                )

        threading.Thread(target=_check, daemon=True).start()
```

`_on_settings_changed` 메서드에 추가 (기존 코드 뒤):
```python
        # 핫키 재등록
        self._hotkey_mgr.stop()
        self._hotkey_mgr.unregister_all()
        self._hotkey_mgr.register(config.hotkey_overlay, self._toggle_overlay)
        self._hotkey_mgr.register(config.hotkey_reset, self._reset_combat)
        self._hotkey_mgr.register(config.hotkey_breakdown, self._toggle_breakdown)
        self._hotkey_mgr.start()
```

`_quit` 메서드에 추가 (pipeline.stop() 전):
```python
        self._hotkey_mgr.stop()
```

**Step 5: Run full test suite**

Run: `pytest tests/test_calculator.py tests/test_session_repository.py tests/test_models.py tests/test_config.py tests/test_combat_logger.py tests/test_parser.py tests/test_hotkey_manager.py tests/test_updater.py -v`
Expected: ALL PASS

**Step 6: Verify import**

Run: `PYTHONPATH=src python3 -c "from aion2meter.app import App; print('OK')"`
Expected: `OK` (PyQt6 필요, 환경에 없으면 ImportError 무시)

---

## 실행 순서 요약

```
Batch 1 (병렬): G1 + G4 + G5 + G6
  ↓
Batch 2 (병렬, G1 완료 후): G2 + G3
  ↓
Batch 3: G7 (통합)
  ↓
최종 검증: pytest 전체 + import 확인
```
