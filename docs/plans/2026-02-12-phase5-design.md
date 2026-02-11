# Phase 5: 타임라인 + 단축키 + 자동 업데이트 + 최적화

> 작성일: 2026-02-12
> 상태: 설계 완료 → 구현 대기

---

## 결정 사항

- **DPS 타임라인**: 오버레이 미니 스파크라인(QPainter) + 리포트 상세(matplotlib)
- **키보드 단축키**: pynput 글로벌 핫키
- **자동 업데이트**: GitHub Releases API (urllib, 의존성 추가 없음)
- **성능 최적화**: 픽셀 샘플링 중복 감지 + 이벤트 히스토리 제한
- **i18n**: 이번 스코프에서 제외

---

## 태스크 (총 7개)

### G1: DPS 타임라인 데이터 모델 [독립] ~80줄
**수정**: `models.py`, `dps_calculator.py`, `session_repository.py`

DPS 값의 시계열 데이터를 추적한다.

**DpsSnapshot 확장:**
```python
dps_timeline: list[tuple[float, float]] = field(default_factory=list)
# (경과초, dps) - 오버레이용 최근 120포인트
```

**Calculator 변경:**
- `_dps_timeline: list[tuple[float, float]]` — 전체 타임라인 저장
- `add_events()` 호출 시 `(elapsed, dps)` 튜플 추가
- 스냅샷에 최근 120포인트만 포함 (오버레이 렌더링용)
- `get_dps_timeline()` — 전체 타임라인 반환 (리포트용)
- `_reset_state()`에서 타임라인 초기화

**SessionRepository 확장:**
```sql
session_timeline(
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    elapsed REAL NOT NULL,
    dps REAL NOT NULL
)
```
- `save_session()`에서 타임라인 일괄 삽입
- `get_session_timeline(id) -> list[dict]`

**테스트**: `tests/test_calculator.py`에 타임라인 테스트 추가

---

### G2: 오버레이 스파크라인 [의존: G1] ~80줄
**신규**: `src/aion2meter/ui/sparkline.py`
**수정**: `overlay.py`

QPainter로 렌더링하는 경량 스파크라인 위젯.

**SparklineWidget(QWidget):**
- 크기: 200×40px
- QPainter로 라인 차트 렌더링 (반투명 배경)
- 데이터: `list[tuple[float, float]]` (경과초, DPS)
- Y축: 0~현재 peak DPS (자동 스케일)
- 색상: 녹색 라인(#00FF64), 반투명 그리드
- `update_data(timeline)` 메서드

**Overlay 통합:**
- peak_label 아래, skill_labels 위에 배치
- breakdown 토글 시 함께 표시/숨기기
- `_SPARKLINE_HEIGHT = 40`
- `_BREAKDOWN_HEIGHT` 조정: 100 → 140 (스파크라인 포함)

---

### G3: 세션 리포트 타임라인 차트 [의존: G1] ~60줄
**수정**: `session_report.py`

**DpsTimelineChart(FigureCanvasQTAgg):**
- matplotlib 라인 차트
- X축: 시간(초), Y축: DPS
- 다크 테마 (검정 배경 + 녹색 라인)
- Peak DPS 수평선 (빨간 점선)
- 평균 DPS 수평선 (노란 점선)

**SessionDetailDialog 확장:**
- 기존 바차트/파이차트 위에 타임라인 차트 추가
- 레이아웃: 타임라인 → 바차트 → 파이차트 (세로)

---

### G4: 키보드 단축키 [독립] ~100줄
**신규**: `src/aion2meter/hotkey_manager.py`
**수정**: `models.py`, `config.py`

**HotkeyManager:**
```python
class HotkeyManager:
    def __init__(self) -> None: ...
    def register(self, hotkey: str, callback: Callable) -> None: ...
    def unregister_all(self) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```
- pynput.keyboard.GlobalHotKeys 사용
- 핫키 문자열 형식: `"<ctrl>+<shift>+o"` (pynput 표준)
- 별도 스레드에서 리스너 실행

**AppConfig 확장:**
```python
hotkey_overlay: str = "<ctrl>+<shift>+o"
hotkey_reset: str = "<ctrl>+<shift>+r"
hotkey_breakdown: str = "<ctrl>+<shift>+b"
```

**ConfigManager 업데이트:** TOML 직렬화/역직렬화

**테스트**: `tests/test_hotkey_manager.py`
- 등록/해제, 중복 등록, 빈 핫키

---

### G5: 자동 업데이트 확인 [독립] ~80줄
**신규**: `src/aion2meter/updater.py`

**UpdateChecker(QThread):**
```python
class UpdateChecker(QThread):
    update_available = pyqtSignal(str, str)  # (latest_version, download_url)

    def __init__(self, current_version: str) -> None: ...
    def run(self) -> None: ...
```
- GitHub API: `https://api.github.com/repos/servaltullius/aion2-dps-meter/releases/latest`
- `urllib.request.urlopen` (추가 의존성 없음)
- tag_name에서 버전 추출, 현재 버전과 비교
- 업데이트 존재 시 시그널 발생

**AppConfig 확장:**
```python
auto_update_check: bool = True
```

**트레이 알림:**
- `tray.showMessage("업데이트 알림", f"새 버전 {version} ...", ...)`
- 메시지 클릭 시 브라우저에서 다운로드 URL 열기

**테스트**: `tests/test_updater.py`
- 버전 비교 로직, JSON 파싱

---

### G6: 성능 최적화 [독립] ~60줄
**수정**: `image_proc.py`, `dps_calculator.py`, `pipeline.py`

**중복 프레임 감지 개선 (image_proc.py):**
- 현재: 전체 이미지 MD5 해시 → 느림
- 변경: 5지점 픽셀 샘플링 (4모서리 + 중앙) 비교
- 이미지 크기 불일치 시 즉시 non-duplicate 반환
- 체감 ~10배 빠름, 정확도 충분

**이벤트 히스토리 제한 (dps_calculator.py):**
- `list` → `collections.deque(maxlen=10000)`
- 메모리 누수 방지 (장시간 실행 시)

**프레임 스킵 최적화 (pipeline.py):**
- OcrWorker: 큐에 2개 이상 쌓이면 최신 1개만 처리
- 캡처가 OCR보다 빠를 때 자연스러운 프레임 드랍

**테스트**: `tests/test_preprocess.py` 업데이트

---

### G7: 앱 통합 [의존: G1-G6] ~60줄
**수정**: `app.py`, `tray_icon.py`, `settings_dialog.py`

**app.py:**
- HotkeyManager 생성/시작/종료
- UpdateChecker 시작, update_available 시그널 처리
- 트레이 알림 표시 + 브라우저 열기

**tray_icon.py:**
- "업데이트 확인" 메뉴 추가
- 시그널: `check_update = pyqtSignal()`

**settings_dialog.py:**
- 단축키 설정 섹션 (3개 QLineEdit)
- 자동 업데이트 체크박스

---

## 실행 순서

```
G1 + G4 + G5 + G6 (병렬, 모두 독립)
  ↓
G2 + G3 (G1 완료 후, 병렬)
  ↓
G7 (전체 완료 후)
```

## 신규 의존성

| 패키지 | 용도 | 그룹 |
|--------|------|------|
| pynput | 글로벌 키보드 단축키 | dependencies |

## 검증

```bash
pytest -v
python3 -c "from aion2meter.app import App; print('OK')"
```
