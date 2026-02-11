# Phase 6: 세션 태깅 + Discord + 프로파일 + DPS 알림 — TDD 구현 계획

> 설계 문서: `docs/plans/2026-02-12-phase6-design.md`
> 현재 테스트: 137개 통과

---

## H1: 세션 태깅 [독립]

### H1-Step1: RED — 세션 태그 저장/조회 테스트 작성

**파일**: `tests/test_session_repository.py`

기존 `_sample_snapshot()`, `_sample_events()`, `repo` fixture 재사용.

```python
# tests/test_session_repository.py 맨 아래에 추가

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
```

**실행**: `pytest tests/test_session_repository.py::TestSessionTag -v` → 6 FAIL

### H1-Step2: GREEN — session_repository.py 수정

**파일**: `src/aion2meter/io/session_repository.py`

변경 1 — `_SCHEMA`에 `tag` 컬럼 추가:
```python
# sessions 테이블 정의에서
_SCHEMA = """\
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time  REAL NOT NULL,
    end_time    REAL,
    total_damage INTEGER DEFAULT 0,
    peak_dps    REAL DEFAULT 0.0,
    avg_dps     REAL DEFAULT 0.0,
    event_count INTEGER DEFAULT 0,
    duration    REAL DEFAULT 0.0,
    tag         TEXT DEFAULT ''
);
... (나머지 테이블 동일)
"""
```

변경 2 — `__init__`에 마이그레이션 추가:
```python
def __init__(self, db_path: Path | None = None) -> None:
    self._db_path = db_path or _DEFAULT_DB_PATH
    self._db_path.parent.mkdir(parents=True, exist_ok=True)
    self._conn = sqlite3.connect(str(self._db_path))
    self._conn.row_factory = sqlite3.Row
    self._conn.execute("PRAGMA foreign_keys = ON")
    self._conn.executescript(_SCHEMA)
    self._migrate()

def _migrate(self) -> None:
    """기존 DB에 누락된 컬럼을 추가한다."""
    cur = self._conn.execute("PRAGMA table_info(sessions)")
    columns = {row[1] for row in cur.fetchall()}
    if "tag" not in columns:
        self._conn.execute("ALTER TABLE sessions ADD COLUMN tag TEXT DEFAULT ''")
        self._conn.commit()
```

변경 3 — `save_session` 시그니처 변경:
```python
def save_session(
    self, events: list[DamageEvent], snapshot: DpsSnapshot, tag: str = ""
) -> int:
    # INSERT에 tag 추가
    cur = self._conn.execute(
        "INSERT INTO sessions "
        "(start_time, end_time, total_damage, peak_dps, avg_dps, event_count, duration, tag) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (start_time, end_time, snapshot.total_damage, snapshot.peak_dps,
         avg_dps, snapshot.event_count, duration, tag),
    )
    # ... 나머지 동일
```

변경 4 — `list_sessions` 확장:
```python
def list_sessions(self, limit: int = 50, tag_filter: str = "") -> list[dict]:
    if tag_filter:
        cur = self._conn.execute(
            "SELECT * FROM sessions WHERE tag = ? ORDER BY start_time DESC LIMIT ?",
            (tag_filter, limit),
        )
    else:
        cur = self._conn.execute(
            "SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?",
            (limit,),
        )
    return [dict(row) for row in cur.fetchall()]
```

**실행**: `pytest tests/test_session_repository.py -v` → ALL PASS

### H1-Step3: TagInputDialog UI

**파일**: `src/aion2meter/ui/tag_input_dialog.py` (신규)

```python
"""전투 종료 시 태그 입력 다이얼로그."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class TagInputDialog(QDialog):
    """전투 종료 시 세션에 태그를 입력하는 다이얼로그."""

    tag_submitted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("세션 태그")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("세션에 태그를 입력하세요 (보스명, 메모 등):"))

        self._input = QLineEdit()
        self._input.setPlaceholderText("예: 바하무트, 연습")
        self._input.returnPressed.connect(self._submit)
        layout.addWidget(self._input)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("저장")
        save_btn.clicked.connect(self._submit)
        skip_btn = QPushButton("건너뛰기")
        skip_btn.clicked.connect(self._skip)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(skip_btn)
        layout.addLayout(btn_layout)

    def _submit(self) -> None:
        self.tag_submitted.emit(self._input.text().strip())
        self.accept()

    def _skip(self) -> None:
        self.tag_submitted.emit("")
        self.accept()
```

**실행**: `python3 -c "from aion2meter.ui.tag_input_dialog import TagInputDialog; print('OK')"` → OK

---

## H2: Discord Webhook [독립]

### H2-Step1: RED — Discord Embed 생성 + URL 검증 테스트

**파일**: `tests/test_discord_notifier.py` (신규)

```python
"""Discord 알림 단위 테스트."""

from __future__ import annotations

import json

import pytest

from aion2meter.io.discord_notifier import DiscordNotifier
from aion2meter.models import DpsSnapshot


def _sample_snapshot() -> DpsSnapshot:
    return DpsSnapshot(
        dps=2750.0,
        total_damage=5500,
        elapsed_seconds=2.0,
        peak_dps=3100.0,
        combat_active=False,
        skill_breakdown={"검격": 2300, "마법": 3200},
        event_count=3,
    )


class TestBuildEmbed:
    """Embed JSON 생성 검증."""

    def test_embed_has_required_fields(self) -> None:
        """Embed에 title, fields, color가 있다."""
        embed = DiscordNotifier.build_embed(_sample_snapshot(), tag="보스1")
        assert "title" in embed
        assert "fields" in embed
        assert "color" in embed

    def test_embed_fields_include_dps(self) -> None:
        """fields에 DPS 정보가 포함된다."""
        embed = DiscordNotifier.build_embed(_sample_snapshot(), tag="")
        field_names = [f["name"] for f in embed["fields"]]
        assert "DPS" in field_names
        assert "총 대미지" in field_names
        assert "Peak DPS" in field_names

    def test_embed_includes_tag_when_provided(self) -> None:
        """태그가 있으면 footer에 표시된다."""
        embed = DiscordNotifier.build_embed(_sample_snapshot(), tag="보스A")
        assert "footer" in embed
        assert "보스A" in embed["footer"]["text"]

    def test_embed_no_footer_without_tag(self) -> None:
        """태그가 없으면 footer가 없다."""
        embed = DiscordNotifier.build_embed(_sample_snapshot(), tag="")
        assert "footer" not in embed

    def test_embed_top3_skills(self) -> None:
        """스킬 Top 3가 표시된다."""
        embed = DiscordNotifier.build_embed(_sample_snapshot(), tag="")
        field_names = [f["name"] for f in embed["fields"]]
        assert "스킬 Top 3" in field_names


class TestWebhookValidation:
    """Webhook URL 검증."""

    def test_valid_discord_url(self) -> None:
        url = "https://discord.com/api/webhooks/123/abc"
        assert DiscordNotifier.is_valid_webhook_url(url) is True

    def test_invalid_url(self) -> None:
        assert DiscordNotifier.is_valid_webhook_url("") is False
        assert DiscordNotifier.is_valid_webhook_url("http://example.com") is False

    def test_discordapp_url_also_valid(self) -> None:
        url = "https://discordapp.com/api/webhooks/123/abc"
        assert DiscordNotifier.is_valid_webhook_url(url) is True
```

**실행**: `pytest tests/test_discord_notifier.py -v` → 7 FAIL (모듈 없음)

### H2-Step2: GREEN — discord_notifier.py 구현

**파일**: `src/aion2meter/io/discord_notifier.py` (신규)

```python
"""Discord Webhook 알림."""

from __future__ import annotations

import json
import logging
import urllib.request
from urllib.error import URLError

from aion2meter.models import DpsSnapshot

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """Discord Webhook으로 세션 요약을 전송한다."""

    @staticmethod
    def build_embed(snapshot: DpsSnapshot, tag: str = "") -> dict:
        """Discord Embed JSON을 생성한다."""
        duration_str = f"{snapshot.elapsed_seconds:.1f}초"

        # 스킬 Top 3
        sorted_skills = sorted(
            snapshot.skill_breakdown.items(), key=lambda x: x[1], reverse=True
        )[:3]
        skill_text = "\n".join(
            f"{name}: {dmg:,}" for name, dmg in sorted_skills
        ) or "없음"

        fields = [
            {"name": "DPS", "value": f"{snapshot.dps:,.1f}", "inline": True},
            {"name": "총 대미지", "value": f"{snapshot.total_damage:,}", "inline": True},
            {"name": "지속시간", "value": duration_str, "inline": True},
            {"name": "Peak DPS", "value": f"{snapshot.peak_dps:,.1f}", "inline": True},
            {"name": "스킬 Top 3", "value": skill_text, "inline": False},
        ]

        embed: dict = {
            "title": "전투 요약",
            "color": 0x00FF64,
            "fields": fields,
        }

        if tag:
            embed["footer"] = {"text": f"태그: {tag}"}

        return embed

    @staticmethod
    def is_valid_webhook_url(url: str) -> bool:
        """Discord Webhook URL 형식을 검증한다."""
        if not url:
            return False
        return url.startswith("https://discord.com/api/webhooks/") or url.startswith(
            "https://discordapp.com/api/webhooks/"
        )

    @staticmethod
    def send_session_summary(
        snapshot: DpsSnapshot, tag: str, webhook_url: str
    ) -> bool:
        """세션 요약을 Discord로 전송한다."""
        if not DiscordNotifier.is_valid_webhook_url(webhook_url):
            logger.warning("잘못된 Discord Webhook URL: %s", webhook_url)
            return False

        embed = DiscordNotifier.build_embed(snapshot, tag)
        payload = json.dumps({"embeds": [embed]}).encode("utf-8")

        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 204
        except (URLError, OSError) as e:
            logger.error("Discord 전송 실패: %s", e)
            return False
```

**실행**: `pytest tests/test_discord_notifier.py -v` → ALL PASS

### H2-Step3: AppConfig + ConfigManager 확장

**파일**: `src/aion2meter/models.py` — AppConfig에 추가:
```python
discord_webhook_url: str = ""
discord_auto_send: bool = False
```

**파일**: `src/aion2meter/config.py` — load/serialize에 추가:
```python
# load()에:
discord_webhook_url=str(data.get("discord_webhook_url", "")),
discord_auto_send=bool(data.get("discord_auto_send", False)),

# _serialize()에:
lines.append(f'discord_webhook_url = "{config.discord_webhook_url}"')
lines.append(f"discord_auto_send = {'true' if config.discord_auto_send else 'false'}")
```

**테스트**: `tests/test_config.py`에 추가:
```python
class TestDiscordConfig:
    """Discord 설정 직렬화/역직렬화."""

    def test_default_discord_config(self):
        config = AppConfig()
        assert config.discord_webhook_url == ""
        assert config.discord_auto_send is False

    def test_discord_config_roundtrip(self, tmp_path):
        config = AppConfig(
            discord_webhook_url="https://discord.com/api/webhooks/123/abc",
            discord_auto_send=True,
        )
        mgr = ConfigManager(default_path=tmp_path / "config.toml")
        mgr.save(config)
        loaded = mgr.load()
        assert loaded.discord_webhook_url == "https://discord.com/api/webhooks/123/abc"
        assert loaded.discord_auto_send is True
```

**실행**: `pytest tests/test_config.py tests/test_discord_notifier.py -v` → ALL PASS

---

## H3: 프로파일 시스템 [독립]

### H3-Step1: RED — 프로파일 CRUD 테스트

**파일**: `tests/test_profile_manager.py` (신규)

```python
"""프로파일 관리 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from aion2meter.models import AppConfig, ROI
from aion2meter.profile_manager import ProfileManager


@pytest.fixture()
def pm(tmp_path: Path) -> ProfileManager:
    return ProfileManager(profiles_path=tmp_path / "profiles.toml")


class TestProfileManager:
    """프로파일 CRUD 검증."""

    def test_list_empty(self, pm: ProfileManager) -> None:
        """초기 프로파일 목록은 비어있다."""
        assert pm.list_profiles() == []

    def test_save_and_list(self, pm: ProfileManager) -> None:
        """프로파일 저장 후 목록에 나타난다."""
        config = AppConfig(
            roi=ROI(left=100, top=200, width=400, height=80),
            ocr_engine="winocr",
            idle_timeout=5.0,
        )
        pm.save_current_as("마법사", config)
        assert "마법사" in pm.list_profiles()

    def test_get_active_default(self, pm: ProfileManager) -> None:
        """프로파일이 없으면 active는 빈 문자열이다."""
        assert pm.get_active() == ""

    def test_switch_profile(self, pm: ProfileManager) -> None:
        """프로파일 전환 시 해당 설정을 반환한다."""
        config = AppConfig(
            roi=ROI(left=100, top=200, width=400, height=80),
            ocr_engine="winocr",
            idle_timeout=5.0,
        )
        pm.save_current_as("마법사", config)
        loaded = pm.switch_profile("마법사")
        assert loaded.roi is not None
        assert loaded.roi.left == 100
        assert loaded.ocr_engine == "winocr"
        assert pm.get_active() == "마법사"

    def test_delete_profile(self, pm: ProfileManager) -> None:
        """프로파일을 삭제하면 목록에서 사라진다."""
        config = AppConfig(ocr_engine="tesseract")
        pm.save_current_as("궁수", config)
        pm.delete_profile("궁수")
        assert "궁수" not in pm.list_profiles()

    def test_switch_nonexistent_raises(self, pm: ProfileManager) -> None:
        """존재하지 않는 프로파일 전환 시 KeyError."""
        with pytest.raises(KeyError):
            pm.switch_profile("없는프로파일")

    def test_multiple_profiles(self, pm: ProfileManager) -> None:
        """여러 프로파일을 저장하고 전환한다."""
        cfg1 = AppConfig(roi=ROI(left=10, top=20, width=100, height=50), ocr_engine="winocr")
        cfg2 = AppConfig(roi=ROI(left=50, top=60, width=200, height=100), ocr_engine="tesseract")
        pm.save_current_as("마법사", cfg1)
        pm.save_current_as("궁수", cfg2)

        loaded = pm.switch_profile("궁수")
        assert loaded.roi is not None
        assert loaded.roi.left == 50
        assert loaded.ocr_engine == "tesseract"
```

**실행**: `pytest tests/test_profile_manager.py -v` → 7 FAIL

### H3-Step2: GREEN — profile_manager.py 구현

**파일**: `src/aion2meter/profile_manager.py` (신규)

```python
"""직업별 프로파일 관리 (TOML)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from aion2meter.models import AppConfig, ROI

_DEFAULT_PATH = Path.home() / ".aion2meter" / "profiles.toml"


class ProfileManager:
    """직업별 ROI/OCR 설정을 TOML 파일로 저장/전환한다."""

    def __init__(self, profiles_path: Path | None = None) -> None:
        self._path = profiles_path or _DEFAULT_PATH
        self._data: dict = self._load_file()

    def _load_file(self) -> dict:
        if not self._path.exists():
            return {"active": "", "profiles": {}}
        with open(self._path, "rb") as f:
            data = tomllib.load(f)
        data.setdefault("active", "")
        data.setdefault("profiles", {})
        return data

    def _save_file(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        lines.append(f'active = "{self._data["active"]}"')

        for name, prof in self._data["profiles"].items():
            lines.append("")
            lines.append(f'[profiles."{name}"]')
            if prof.get("roi_left") is not None:
                lines.append(f"roi_left = {prof['roi_left']}")
                lines.append(f"roi_top = {prof['roi_top']}")
                lines.append(f"roi_width = {prof['roi_width']}")
                lines.append(f"roi_height = {prof['roi_height']}")
            lines.append(f'ocr_engine = "{prof.get("ocr_engine", "winocr")}"')
            lines.append(f"idle_timeout = {prof.get('idle_timeout', 5.0)}")

        lines.append("")
        self._path.write_text("\n".join(lines), encoding="utf-8")

    def list_profiles(self) -> list[str]:
        return list(self._data["profiles"].keys())

    def get_active(self) -> str:
        return self._data["active"]

    def switch_profile(self, name: str) -> AppConfig:
        if name not in self._data["profiles"]:
            raise KeyError(f"프로파일 '{name}'이 존재하지 않습니다.")
        self._data["active"] = name
        self._save_file()
        return self._profile_to_config(self._data["profiles"][name])

    def save_current_as(self, name: str, config: AppConfig) -> None:
        prof: dict = {
            "ocr_engine": config.ocr_engine,
            "idle_timeout": config.idle_timeout,
        }
        if config.roi is not None:
            prof["roi_left"] = config.roi.left
            prof["roi_top"] = config.roi.top
            prof["roi_width"] = config.roi.width
            prof["roi_height"] = config.roi.height
        self._data["profiles"][name] = prof
        self._data["active"] = name
        self._save_file()

    def delete_profile(self, name: str) -> None:
        self._data["profiles"].pop(name, None)
        if self._data["active"] == name:
            self._data["active"] = ""
        self._save_file()

    @staticmethod
    def _profile_to_config(prof: dict) -> AppConfig:
        roi = None
        if prof.get("roi_left") is not None:
            roi = ROI(
                left=int(prof["roi_left"]),
                top=int(prof["roi_top"]),
                width=int(prof["roi_width"]),
                height=int(prof["roi_height"]),
            )
        return AppConfig(
            roi=roi,
            ocr_engine=str(prof.get("ocr_engine", "winocr")),
            idle_timeout=float(prof.get("idle_timeout", 5.0)),
        )
```

**실행**: `pytest tests/test_profile_manager.py -v` → ALL PASS

---

## H4: DPS 알림 시스템 [독립]

### H4-Step1: RED — AlertManager 테스트

**파일**: `tests/test_alert_manager.py` (신규)

```python
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
```

**실행**: `pytest tests/test_alert_manager.py -v` → 6 FAIL

### H4-Step2: GREEN — alert_manager.py 구현

**파일**: `src/aion2meter/alert_manager.py` (신규)

```python
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
```

### H4-Step3: AppConfig 확장

**파일**: `src/aion2meter/models.py` — AppConfig에 추가:
```python
dps_alert_threshold: float = 0.0
dps_alert_cooldown: float = 10.0
```

**파일**: `src/aion2meter/config.py` — load/serialize에 추가:
```python
# load()에:
dps_alert_threshold=float(data.get("dps_alert_threshold", 0.0)),
dps_alert_cooldown=float(data.get("dps_alert_cooldown", 10.0)),

# _serialize()에:
lines.append(f"dps_alert_threshold = {config.dps_alert_threshold}")
lines.append(f"dps_alert_cooldown = {config.dps_alert_cooldown}")
```

**테스트**: `tests/test_config.py`에 추가:
```python
class TestAlertConfig:
    """DPS 알림 설정 직렬화/역직렬화."""

    def test_default_alert_config(self):
        config = AppConfig()
        assert config.dps_alert_threshold == 0.0
        assert config.dps_alert_cooldown == 10.0

    def test_alert_config_roundtrip(self, tmp_path):
        config = AppConfig(dps_alert_threshold=5000.0, dps_alert_cooldown=15.0)
        mgr = ConfigManager(default_path=tmp_path / "config.toml")
        mgr.save(config)
        loaded = mgr.load()
        assert loaded.dps_alert_threshold == 5000.0
        assert loaded.dps_alert_cooldown == 15.0
```

**실행**: `pytest tests/test_alert_manager.py tests/test_config.py -v` → ALL PASS

---

## H5: 앱 통합 [의존: H1-H4]

### H5-Step1: SettingsDialog 확장

**파일**: `src/aion2meter/ui/settings_dialog.py`

form에 추가 (기존 auto_update_check 아래):
```python
# Discord 섹션
form.addRow(QLabel("── Discord ──"), QLabel(""))

self._webhook_url_edit = QLineEdit(config.discord_webhook_url)
self._webhook_url_edit.setPlaceholderText("https://discord.com/api/webhooks/...")
form.addRow("Webhook URL:", self._webhook_url_edit)

self._discord_auto_send_check = QCheckBox("전투 종료 시 자동 전송")
self._discord_auto_send_check.setChecked(config.discord_auto_send)
form.addRow("", self._discord_auto_send_check)

# DPS 알림 섹션
form.addRow(QLabel("── DPS 알림 ──"), QLabel(""))

self._alert_threshold_spin = QSpinBox()
self._alert_threshold_spin.setRange(0, 999999)
self._alert_threshold_spin.setValue(int(config.dps_alert_threshold))
self._alert_threshold_spin.setSuffix(" (0=비활성)")
form.addRow("DPS 임계값:", self._alert_threshold_spin)

self._alert_cooldown_spin = QSpinBox()
self._alert_cooldown_spin.setRange(1, 300)
self._alert_cooldown_spin.setValue(int(config.dps_alert_cooldown))
self._alert_cooldown_spin.setSuffix("초")
form.addRow("알림 쿨다운:", self._alert_cooldown_spin)
```

`_apply()`에 추가:
```python
self._config.discord_webhook_url = self._webhook_url_edit.text().strip()
self._config.discord_auto_send = self._discord_auto_send_check.isChecked()
self._config.dps_alert_threshold = float(self._alert_threshold_spin.value())
self._config.dps_alert_cooldown = float(self._alert_cooldown_spin.value())
```

### H5-Step2: TrayIcon에 프로파일 시그널 추가

**파일**: `src/aion2meter/ui/tray_icon.py`

시그널 추가:
```python
switch_profile = pyqtSignal(str)
save_profile = pyqtSignal()
```

메뉴 구성 — "세션 기록" 메뉴 아래에 추가:
```python
# 프로파일 서브메뉴 (app.py에서 동적으로 채움)
self._profile_menu = QMenu("프로파일", menu)
menu.addMenu(self._profile_menu)
```

`update_profile_menu` 메서드 추가:
```python
def update_profile_menu(self, names: list[str], active: str) -> None:
    """프로파일 메뉴를 갱신한다."""
    self._profile_menu.clear()
    for name in names:
        action = QAction(f"{'● ' if name == active else ''}{name}", self._profile_menu)
        action.triggered.connect(lambda checked, n=name: self.switch_profile.emit(n))
        self._profile_menu.addAction(action)
    if names:
        self._profile_menu.addSeparator()
    save_action = QAction("현재 설정 저장...", self._profile_menu)
    save_action.triggered.connect(self.save_profile.emit)
    self._profile_menu.addAction(save_action)
```

### H5-Step3: app.py 통합

**파일**: `src/aion2meter/app.py`

import 추가:
```python
from aion2meter.alert_manager import AlertManager
from aion2meter.io.discord_notifier import DiscordNotifier
from aion2meter.profile_manager import ProfileManager
from aion2meter.ui.tag_input_dialog import TagInputDialog
```

`__init__`에 추가:
```python
# 알림 매니저
self._alert_mgr = AlertManager(
    threshold=self._config.dps_alert_threshold,
    cooldown=self._config.dps_alert_cooldown,
)

# 프로파일 매니저
self._profile_mgr = ProfileManager()
self._tray.switch_profile.connect(self._switch_profile)
self._tray.save_profile.connect(self._save_profile)
self._update_profile_menu()
```

`_on_dps_updated` 수정:
```python
def _on_dps_updated(self, snapshot: DpsSnapshot) -> None:
    self._overlay.update_display(snapshot)
    # DPS 알림 체크
    alert = self._alert_mgr.check(snapshot)
    if alert:
        msg = (
            f"DPS {alert.current_dps:,.0f} — 임계값 {alert.threshold:,.0f} "
            f"{'초과' if alert.alert_type == 'above' else '미달'}"
        )
        self._tray.showMessage("DPS 알림", msg)
```

`_on_combat_ended` 수정 — 태그 입력 → 저장 → Discord:
```python
def _on_combat_ended(self, events: list, snapshot: object) -> None:
    if not events:
        return
    self._pending_events = events
    self._pending_snapshot = snapshot
    self._tag_dialog = TagInputDialog()
    self._tag_dialog.tag_submitted.connect(self._finish_combat_save)
    self._tag_dialog.show()

def _finish_combat_save(self, tag: str) -> None:
    events = self._pending_events
    snapshot = self._pending_snapshot
    self._session_repo.save_session(events, snapshot, tag=tag)

    # Discord 자동 전송
    if self._config.discord_auto_send and self._config.discord_webhook_url:
        import threading
        threading.Thread(
            target=DiscordNotifier.send_session_summary,
            args=(snapshot, tag, self._config.discord_webhook_url),
            daemon=True,
        ).start()
```

프로파일 메서드 추가:
```python
def _switch_profile(self, name: str) -> None:
    config = self._profile_mgr.switch_profile(name)
    # ROI와 OCR 설정만 프로파일에서 가져옴
    self._config.roi = config.roi
    self._config.ocr_engine = config.ocr_engine
    self._config.idle_timeout = config.idle_timeout
    self._config_manager.save(self._config)
    # 파이프라인 재시작
    self._pipeline.stop()
    self._pipeline = DpsPipeline(config=self._config)
    self._pipeline.dps_updated.connect(self._on_dps_updated)
    self._pipeline._calculator.set_on_reset(self._on_combat_ended)
    if self._config.roi is not None:
        self._pipeline.start(self._config.roi)
    self._update_profile_menu()

def _save_profile(self) -> None:
    from PyQt6.QtWidgets import QInputDialog
    name, ok = QInputDialog.getText(None, "프로파일 저장", "프로파일 이름:")
    if ok and name.strip():
        self._profile_mgr.save_current_as(name.strip(), self._config)
        self._update_profile_menu()

def _update_profile_menu(self) -> None:
    names = self._profile_mgr.list_profiles()
    active = self._profile_mgr.get_active()
    self._tray.update_profile_menu(names, active)
```

`_on_settings_changed`에 알림 설정 반영 추가:
```python
# AlertManager 재생성
self._alert_mgr = AlertManager(
    threshold=config.dps_alert_threshold,
    cooldown=config.dps_alert_cooldown,
)
```

`_quit`에서 pending 처리 — tag_dialog 없이 바로 저장:
```python
# 활성 세션 저장 (태그 없이)
events = self._pipeline.get_event_history()
if events:
    snapshot = self._pipeline._calculator.add_events([])
    self._session_repo.save_session(events, snapshot, tag="")
```

### H5-Step4: 최종 검증

**실행**:
```bash
pytest -v
python3 -c "from aion2meter.app import App; print('OK')"
```

---

## 실행 순서

```
H1 + H2 + H3 + H4 (병렬, 모두 독립)
  ↓
H5 (통합)
```

## 예상 테스트 수

| 태스크 | 신규 테스트 |
|--------|------------|
| H1     | 6          |
| H2     | 7 + 2      |
| H3     | 7          |
| H4     | 6 + 2      |
| **합계** | **30**   |

현재 137 → 목표 **167개 이상**

---

## 검증 명령어

```bash
# 전체 테스트
pytest -v

# import 검증
python3 -c "from aion2meter.app import App; print('OK')"

# 개별 모듈 검증
python3 -c "from aion2meter.io.discord_notifier import DiscordNotifier; print('OK')"
python3 -c "from aion2meter.profile_manager import ProfileManager; print('OK')"
python3 -c "from aion2meter.alert_manager import AlertManager; print('OK')"
python3 -c "from aion2meter.ui.tag_input_dialog import TagInputDialog; print('OK')"
```
