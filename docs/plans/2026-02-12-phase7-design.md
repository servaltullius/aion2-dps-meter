# Phase 7: OCR/핵심 엔진 개선 설계

## 배경

Phase 1~6 완료 상태. 168개 테스트 통과.
현재 OCR 파이프라인은 기본적인 전처리(2x 업스케일 → 색상 마스크 → 이진화)만 수행하며,
게임 내 배경 노이즈, 텍스트 겹침, 저해상도 등으로 인식률이 저하되는 문제가 있음.

## 목표

1. **전처리 파이프라인 고도화** — 노이즈 제거, 샤프닝, 적응적 이진화 추가
2. **EasyOCR 엔진 추가** — winocr/tesseract 외 딥러닝 기반 OCR 대안
3. **파서 강화** — fuzzy 매칭, 새 패턴(miss/resist/heal), OCR 보정 확장
4. **OCR 디버그 도구** — 인식 실패 원인 분석을 위한 프레임 덤프

## 범위 결정

전체 아이디어 중 **즉시 효과가 큰 것**만 Phase 7a로 구현:

| 태스크 | 효과 | 복잡도 | Phase 7a |
|--------|------|--------|----------|
| 전처리 강화 | 높음 | 낮음 | O |
| EasyOCR | 중간 | 중간 | O |
| 파서 강화 | 중간 | 낮음 | O |
| OCR 디버그 | 보조 | 낮음 | O |
| 다중 ROI | 높음 | 높음 | Phase 7b |
| 자동 ROI 감지 | 중간 | 높음 | Phase 7b |
| OCR 앙상블 | 중간 | 중간 | Phase 7b |

---

## P1: 전처리 파이프라인 고도화

**수정 파일**: `src/aion2meter/preprocess/image_proc.py`

### 현재 파이프라인
```
2x upscale → color_mask → binary
```

### 개선 파이프라인
```
2x upscale → denoise → sharpen → color_mask → adaptive_threshold → cleanup
```

### 새 전처리 스텝

1. **Denoise (노이즈 제거)**
   - `cv2.morphologyEx(MORPH_OPEN)` + `cv2.morphologyEx(MORPH_CLOSE)`
   - 커널 크기 3x3 (작은 노이즈만 제거, 텍스트 보존)

2. **Sharpen (샤프닝)**
   - Unsharp mask: `cv2.GaussianBlur` → 원본 - 블러 → 원본 + 차이
   - OCR에 적합한 날카로운 텍스트 경계 생성

3. **Adaptive Threshold (적응적 이진화)**
   - 기존: `np.where(mask > 0, 255, 0)` (글로벌 이진화)
   - 개선: `cv2.adaptiveThreshold(ADAPTIVE_THRESH_GAUSSIAN_C)` 또는 color mask 후 cleanup
   - 불균일한 조명/배경에 강건

4. **Cleanup (후처리)**
   - 작은 컴포넌트 제거 (`cv2.connectedComponentsWithStats`)
   - 텍스트 크기 미만인 blob 삭제

### AppConfig 확장

```python
@dataclass
class PreprocessConfig:
    upscale_factor: int = 2
    denoise: bool = True
    sharpen: bool = True
    adaptive_threshold: bool = False  # 기본 OFF (색상 마스크가 주력)
    cleanup_min_area: int = 10
```

- `AppConfig.preprocess` 필드 추가 (기본값: PreprocessConfig())
- 기존 동작과 완전 하위 호환

### 테스트

- 합성 이미지(텍스트 + 노이즈)로 전처리 스텝별 출력 검증
- 기존 `test_preprocess.py` 통과 확인

---

## P2: EasyOCR 엔진 추가

**신규 파일**: `src/aion2meter/ocr/easyocr_engine.py`
**수정 파일**: `src/aion2meter/ocr/engine_manager.py`, `src/aion2meter/pipeline/pipeline.py`

### EasyOcrEngine

```python
class EasyOcrEngine:
    """EasyOCR 기반 OCR 엔진. OcrEngine Protocol 구현."""

    def __init__(self, gpu: bool = True, lang: list[str] | None = None):
        self._reader = None  # lazy init
        self._gpu = gpu
        self._lang = lang or ["ko", "en"]

    def _ensure_reader(self):
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(self._lang, gpu=self._gpu)

    def recognize(self, image: np.ndarray) -> OcrResult:
        self._ensure_reader()
        results = self._reader.readtext(image)
        # results: [(bbox, text, confidence), ...]
        text = "\n".join(r[1] for r in results)
        avg_conf = sum(r[2] for r in results) / max(len(results), 1)
        return OcrResult(text=text, confidence=avg_conf, timestamp=time.time())
```

### 엔진 매니저 확장

- `OcrEngineManager`에 `mode` 파라미터 추가: `"failover"` (기존) | `"best_confidence"`
- `best_confidence` 모드: 두 엔진 모두 실행 → confidence 높은 쪽 채택
- 성능 고려: best_confidence 모드는 2x 느림 → 기본값은 failover 유지

### 의존성

- `pyproject.toml`에 optional dependency: `easyocr = {version = ">=1.7", optional = true}`
- extra: `pip install aion2meter[easyocr]`
- EasyOCR가 없으면 ImportError → engine_manager가 자동으로 다음 엔진 시도

### AppConfig 확장

```python
ocr_engine: str = "winocr"  # "winocr" | "tesseract" | "easyocr"
ocr_fallback: str = ""       # 빈 문자열이면 fallback 없음
ocr_mode: str = "failover"   # "failover" | "best_confidence"
```

### 테스트

- Mock reader로 Protocol 준수 검증
- lazy init 확인 (import 에러 시 RuntimeError)
- engine_manager best_confidence 모드 테스트

---

## P3: 파서 강화

**수정 파일**: `src/aion2meter/parser/combat_parser.py`

### 새 패턴

1. **Miss/Resist 패턴**
   ```
   {target}에게 {skill}[을를] 사용했지만 빗나갔습니다
   {target}에게 {skill}[을를] 사용했지만 저항했습니다
   ```
   - `DamageEvent(damage=0, hit_type=HitType.MISS)` 또는 새 `HitType.RESIST`

2. **Heal 패턴** (정보성)
   ```
   {target}에게 {skill}[을를] 사용해 {amount}만큼 회복했습니다
   ```
   - 별도 `HealEvent` 또는 DamageEvent에 `is_heal=True` 플래그

### OCR 보정 확장

```python
# 키워드 보정 추가
_OCR_TEXT_CORRECTIONS = {
    "대머지": "대미지",
    "대미저": "대미지",
    "대머저": "대미지",
    "사용혜": "사용해",
    "사웅해": "사용해",
    "줬숨니다": "줬습니다",
    "줬습나다": "줬습니다",
    "줬숩니다": "줬습니다",
    "빗나갔숨니다": "빗나갔습니다",
    "저항했숨니다": "저항했습니다",
}

# 숫자 보정 확장
_OCR_DIGIT_MAP = {
    "O": "0", "o": "0", "l": "1", "I": "1",
    "B": "8", "S": "5", "Z": "2", "G": "6",
    "D": "0", "Q": "0", "U": "0",  # 추가
}
```

### Fuzzy 매칭

- 정규식 매칭 실패 시, 핵심 키워드("에게", "대미지", "사용") 위치 기반 fallback 파싱
- 편집 거리가 아닌 substring 매칭 (성능 중시)
- 대미지 숫자 추출만 성공하면 이벤트 생성

### HitType 확장

```python
class HitType(Enum):
    NORMAL = "일반"
    PERFECT = "완벽"
    CRITICAL = "치명타"
    STRONG = "강타"
    STRONG_CRITICAL = "강타 치명타"
    PERFECT_CRITICAL = "완벽 치명타"
    MISS = "빗나감"
    RESIST = "저항"
```

### 테스트

- miss/resist 파싱 테스트
- 확장된 OCR 보정 테스트
- fuzzy fallback 파싱 테스트
- 기존 파서 테스트 하위 호환

---

## P4: OCR 디버그 도구

**신규 파일**: `src/aion2meter/io/ocr_debugger.py`

### OcrDebugger

```python
class OcrDebugger:
    """OCR 디버그 정보를 파일로 덤프한다."""

    def __init__(self, output_dir: Path, enabled: bool = False):
        self._output_dir = output_dir
        self._enabled = enabled
        self._counter = 0

    def dump(self, raw_frame, processed_image, ocr_text, parsed_events):
        """한 프레임의 전체 파이프라인 결과를 저장."""
        if not self._enabled:
            return
        self._counter += 1
        frame_dir = self._output_dir / f"frame_{self._counter:06d}"
        frame_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(frame_dir / "raw.png"), raw_frame)
        cv2.imwrite(str(frame_dir / "processed.png"), processed_image)
        (frame_dir / "ocr.txt").write_text(ocr_text, encoding="utf-8")
        (frame_dir / "events.json").write_text(
            json.dumps([asdict(e) for e in parsed_events], ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
```

### AppConfig 확장

```python
ocr_debug: bool = False  # True이면 프레임 덤프 활성화
```

### 파이프라인 연동

- `OcrWorker`에 optional `OcrDebugger` 주입
- 매 프레임 처리 후 `debugger.dump()` 호출
- 성능 영향 최소화: 파일 I/O를 별도 스레드로 분리 가능 (필요 시)

### 테스트

- 덤프 파일 생성 검증
- enabled=False 시 파일 미생성 검증

---

## 태스크 의존 그래프

```
P1 (전처리) ─────┐
P2 (EasyOCR) ────┤
P3 (파서) ────────┤──→ P5 (통합 테스트 + 설정 UI)
P4 (디버그) ──────┘
```

P1, P2, P3, P4는 모두 독립적으로 병렬 구현 가능.

## 예상 규모

| 태스크 | 코드 | 테스트 |
|--------|------|--------|
| P1 전처리 | ~90줄 수정 | ~40줄 |
| P2 EasyOCR | ~60줄 신규 | ~40줄 |
| P3 파서 | ~80줄 수정 | ~60줄 |
| P4 디버그 | ~50줄 신규 | ~30줄 |
| P5 통합 | ~60줄 수정 | ~20줄 |
| **합계** | **~340줄** | **~190줄** |

## 리스크

1. **EasyOCR 의존성 크기**: PyTorch + 모델 파일 ~1GB. exe 빌드 크기 급증.
   - 완화: optional dependency로 분리. exe 빌드에는 포함하지 않음.
2. **전처리 과도 적용**: 샤프닝이나 노이즈 제거가 오히려 텍스트를 훼손할 수 있음.
   - 완화: 각 스텝 on/off 가능. A/B 테스트로 최적 조합 탐색.
3. **파서 fuzzy 매칭 오탐**: 느슨한 매칭이 잘못된 이벤트 생성.
   - 완화: 대미지 숫자가 반드시 존재해야 이벤트 생성.
