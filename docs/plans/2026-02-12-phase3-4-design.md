# Phase 3 & 4: 분석/리포트 + 배포 설계

> 작성일: 2026-02-12
> 상태: 브레인스토밍 완료 → 구현 대기

---

## 결정 사항

- **차트**: matplotlib + FigureCanvasQTAgg (PyQt6 임베딩)
- **빌드**: PyInstaller (`--onefile --windowed`)
- **범위**: Phase 3 + 4 전부 한 사이클

---

## 태스크 (총 6개)

### F1: SQLite 세션 저장소 [독립] ~120줄
**신규**: `src/aion2meter/io/session_repository.py`

DB 위치: `~/.aion2meter/sessions.db`

**스키마:**
```sql
sessions(id, start_time, end_time, total_damage, peak_dps, avg_dps, event_count, duration)
session_events(id, session_id FK, timestamp, source, target, skill, damage, hit_type, is_additional)
skill_summaries(session_id FK, skill, total_damage, hit_count, PK(session_id, skill))
```

**API:**
- `save_session(events, snapshot) -> int`
- `list_sessions(limit=50) -> list[dict]`
- `get_session(id) -> dict | None`
- `get_session_events(id) -> list[dict]`
- `get_skill_summary(id) -> list[dict]`
- `delete_session(id) -> None`

**테스트**: `tests/test_session_repository.py`

---

### F2: 로깅 시스템 [독립] ~30줄
**신규**: `src/aion2meter/logging_config.py`

- 표준 `logging` 모듈
- 파일 로그: `~/.aion2meter/logs/aion2meter.log`
- 콘솔 + 파일 핸들러 병행
- 적용: app.py, pipeline.py, dps_calculator.py, session_repository.py

---

### F3: 세션 리포트 UI + 차트 [의존: F1] ~200줄
**신규**: `src/aion2meter/ui/session_report.py`

**SessionListDialog:**
- QTableWidget: 날짜, 지속시간, 총 대미지, 평균 DPS, Peak DPS
- 행 더블클릭 → 상세 리포트
- "삭제" 버튼

**SessionDetailDialog:**
- 세션 요약 (시간, DPS, 총 대미지)
- matplotlib 수평 바차트 (스킬별 대미지, 상위 10)
- matplotlib 파이차트 (스킬별 비율)
- 다크 테마 (검정 배경 + 녹색)
- CSV/JSON 내보내기 버튼

---

### F4: 세션 비교 [의존: F3] ~120줄
**신규**: `src/aion2meter/ui/session_compare.py`

**SessionCompareDialog:**
- 세션 2개 선택
- 나란히 subplot(1,2) 바차트
- 요약 테이블: DPS 차이(%), Peak DPS 차이

---

### F5: 앱 통합 [의존: F1,F3,F4] ~80줄
**수정**: `tray_icon.py`, `app.py`, `dps_calculator.py`

- 트레이 메뉴: "세션 기록", "세션 비교" 추가
- 전투 리셋 시 자동 `save_session()`
- DpsCalculator에 자동 리셋 콜백 (세션 저장 트리거)
- 종료 시 활성 세션 저장

---

### F6: PyInstaller 빌드 [의존: F5] ~40줄
**신규**: `aion2meter.spec`, `scripts/build.py`

- `--onefile --windowed --name aion2meter`
- hidden imports: matplotlib, winocr, pytesseract
- pyproject.toml에 build 의존성 추가

---

## 실행 순서

```
F1 + F2 (병렬)
  ↓
F3 (F1 완료 후)
  ↓
F4 (F3 완료 후)
  ↓
F5 (F1,F3,F4 완료 후)
  ↓
F6 (최종)
```

## 신규 의존성

| 패키지 | 용도 | 그룹 |
|--------|------|------|
| matplotlib | 차트 | dependencies |
| pyinstaller | exe 빌드 | optional (build) |

## 검증

```bash
pytest -v
python -c "from aion2meter.app import App; print('OK')"
```
