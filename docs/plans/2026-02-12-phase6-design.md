# Phase 6: 세션 태깅 + Discord + 프로파일 + DPS 알림

> 작성일: 2026-02-12
> 상태: 설계 완료 → 구현 대기

---

## 결정 사항

- **세션 태깅**: 수동 태그 입력 (보스명/메모)
- **Discord**: 전투 종료 시 자동 webhook 전송 (Embed)
- **프로파일**: 직업별 ROI/OCR 설정 저장/전환 (TOML)
- **DPS 알림**: 임계값 초과/미달 시 트레이 알림 + 오버레이 피드백
- **테마**: 제외
- **신규 의존성**: 없음

---

## 태스크 (총 5개)

### H1: 세션 태깅 [독립] ~100줄
**수정**: `session_repository.py`, `session_report.py`
**신규**: `src/aion2meter/ui/tag_input_dialog.py`

**DB 변경:**
- `sessions` 테이블에 `tag TEXT DEFAULT ''` 컬럼 추가
- `ALTER TABLE` 마이그레이션 (기존 DB 호환)

**API 변경:**
- `save_session(events, snapshot, tag="") -> int`
- `list_sessions(limit=50, tag_filter="") -> list[dict]`

**UI:**
- `TagInputDialog(QDialog)`: QLineEdit + "저장"/"건너뛰기" 버튼
- 전투 종료 시 팝업
- 세션 목록에 "태그" 컬럼 추가
- 태그 필터링 QLineEdit (목록 상단)

**테스트**: tag 저장, 필터링, 빈 태그, 마이그레이션 4개

---

### H2: Discord Webhook [독립] ~80줄
**신규**: `src/aion2meter/io/discord_notifier.py`
**수정**: `models.py`, `config.py`

**DiscordNotifier:**
- `send_session_summary(snapshot, tag, webhook_url) -> bool`
- `build_embed(snapshot, tag) -> dict` — Embed JSON 생성
- `urllib.request.urlopen`으로 POST (추가 의존성 없음)

**Embed 필드:** DPS, 총 대미지, 지속시간, Peak DPS, 스킬 Top 3, 태그

**AppConfig 확장:**
```python
discord_webhook_url: str = ""
discord_auto_send: bool = False
```

**동작:** 전투 종료 → 태그 저장 후 → auto_send=True + URL 있으면 → 백그라운드 스레드로 전송

**테스트**: Embed 생성 3개, URL 검증 1개

---

### H3: 프로파일 시스템 [독립] ~120줄
**신규**: `src/aion2meter/profile_manager.py`

**저장 위치:** `~/.aion2meter/profiles.toml`

**구조:**
```toml
active = "마법사"

[profiles.마법사]
roi_left = 100
roi_top = 200
roi_width = 400
roi_height = 80
ocr_engine = "winocr"
idle_timeout = 5.0
```

**ProfileManager API:**
- `list_profiles() -> list[str]`
- `get_active() -> str`
- `switch_profile(name) -> AppConfig`
- `save_current_as(name, config)`
- `delete_profile(name)`

**테스트**: 저장/로드/전환/삭제/빈 프로파일 5개

---

### H4: DPS 알림 시스템 [독립] ~80줄
**신규**: `src/aion2meter/alert_manager.py`
**수정**: `models.py`, `config.py`

**AlertManager:**
```python
class AlertManager:
    def __init__(self, threshold: float, cooldown: float = 10.0): ...
    def check(self, snapshot: DpsSnapshot) -> AlertEvent | None: ...
```

**AlertEvent:**
```python
@dataclass(frozen=True)
class AlertEvent:
    alert_type: str      # "above" | "below"
    threshold: float
    current_dps: float
    timestamp: float
```

**동작:**
- DPS가 임계값을 처음 초과 → "above" 알림
- DPS가 임계값 아래로 → "below" 알림
- 쿨다운(10초): 같은 유형 반복 방지

**AppConfig 확장:**
```python
dps_alert_threshold: float = 0.0  # 0이면 비활성
dps_alert_cooldown: float = 10.0
```

**테스트**: 초과 감지, 미달 감지, 쿨다운, 비활성 4개

---

### H5: 앱 통합 [의존: H1-H4] ~100줄
**수정**: `app.py`, `tray_icon.py`, `settings_dialog.py`, `config.py`

**트레이 메뉴:**
- "프로파일" 서브메뉴: 프로파일 목록 + "현재 설정 저장..."

**SettingsDialog 확장:**
- Discord 섹션: webhook URL + 자동 전송 체크박스
- DPS 알림 섹션: 임계값 + 쿨다운

**app.py:**
- AlertManager: `_on_dps_updated()`에서 체크 → 알림 표시
- `_on_combat_ended()` 흐름: 태그 입력 → 세션 저장 → Discord 전송
- ProfileManager: 트레이에서 전환 시 파이프라인 재시작

---

## 실행 순서

```
H1 + H2 + H3 + H4 (병렬, 모두 독립)
  ↓
H5 (통합)
```

## 검증

```bash
pytest -v
python3 -c "from aion2meter.app import App; print('OK')"
```
