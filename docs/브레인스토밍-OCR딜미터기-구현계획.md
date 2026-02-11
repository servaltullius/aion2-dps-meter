# 아이온2 OCR 기반 딜 미터기 - 브레인스토밍 & 구현 계획

> 작성일: 2026-02-12
> 기반 문서: 아이온2 실시간 라이브 OCR 기반 딜 미터기 가능성 평가.md
> 상태: 웹 조사 완료 → 브레인스토밍 결과 정리

---

## 1. 웹 조사 핵심 발견사항

### 1.1 기존 오픈소스 프로젝트

| 프로젝트 | 방식 | 기술 스택 | 특징 |
|---------|------|----------|------|
| [ProjackL2/aion2_dps_meter](https://github.com/ProjackL2/aion2_dps_meter) | **OCR** | Python 3.12 + Tesseract + OpenCV + mss | 한/영 지원, 멀티스레드 OCR, 색상 마스크 |
| [TK-open-public/Aion2-Dps-Meter](https://github.com/TK-open-public/Aion2-Dps-Meter) | 패킷 | Kotlin + JavaScript (Electron) + Npcap | 정확도 높음, 패킷 암호화 시 무력화 |
| [taengu/Aion2-Dps-Meter](https://github.com/taengu/Aion2-Dps-Meter) | 패킷 | Kotlin + JavaScript | 대만/한국 서버 지원, VPN 호환 |

**기존 OCR 프로젝트(ProjackL2) 분석:**
- 캡처 영역: x=94, y=80, w=348, h=852 (config.ini 수동 설정)
- OCR 설정: Tesseract OEM 3, PSM 6, FPS=10, 8스레드 병렬
- 전처리: 2x 업스케일(cv2.INTER_NEAREST_EXACT), BGR 색상 범위별 멀티 마스크
- 색상 코딩(BGR): 흰[182-255,144-200,100-140], 주황[170-255,105-160,32-51], 빨강[100-195,26-31,10-31], 파랑[14-16,85-152,134-248], 초록[59-129,93-202,0-1]

### 1.2 전투 로그 형식 (검증된 정규식)

**한국어:**
```
{대상}에게 {스킬명}[을/를] 사용해 [완벽/치명타/강타/...]{숫자}의 대미지를 줬습니다.
{대상}에게 {숫자}의 추가 대미지를 줬습니다.
```

**한국어 정규식:**
```regex
(.*?)에게 (.*?)\[을를\] 사용해 (\[?완벽\]?|\[?치명타\]?|\[?강타\]?|\[?강타 치명타\]?|\[?완벽 치명타\]?|)([0-9]+[0-9.]*) *의 대미지를 줬습니다\.
```
그룹: 1=대상, 2=스킬, 3=배율유형, 4=데미지

### 1.3 OCR 엔진 벤치마크

| 엔진 | 정확도(신뢰도) | CPU 속도 | GPU 속도 | 한국어 | 설치 |
|------|--------------|---------|---------|--------|------|
| **PaddleOCR PP-OCRv5** | 0.93 | 수십ms (Mobile) | 더 빠름 | 전용 모델 있음 | PaddlePaddle 필요 (무거움) |
| **Tesseract 5.x** | 0.89 | ~1000ms | 미지원 | 지원 | 별도 설치 |
| **EasyOCR** | 0.85 | ~1000ms | ~140ms | 지원 | PyTorch 필요 |
| **Windows OCR (winocr)** | 합리적 | ~48ms/장 | 미지원 | 언어팩 필요 | pip install winocr |

**핵심 인사이트:**
- winocr이 속도 대비 가장 가벼움 (48ms/장, OS 내장, 의존성 최소)
- PaddleOCR은 정확도 최고지만 PaddlePaddle 의존성이 무거움
- Tesseract는 검증됐지만 느림 → 숫자 전용 whitelist로 보완 가능
- **게임 전투 로그는 렌더링 폰트이므로 일반 OCR보다 정확도 높을 가능성**

### 1.4 화면 캡처 벤치마크

| 라이브러리 | FPS | API | 유지보수 |
|-----------|-----|-----|---------|
| **BetterCam** | 123+ | Desktop Duplication | 활발 |
| **DXcam** | 39~239 | Desktop Duplication | 비활성 |
| **mss** | 34~76 | GDI | 활발 |
| **D3DShot** | ~118 | Desktop Duplication | 중단 |

**결론:** OCR 병목(50-1000ms)이 캡처(4-30ms)보다 훨씬 크므로 mss로 충분. 전체화면 캡처 필요 시 BetterCam.

### 1.5 운영정책 & 리스크 분석

| 항목 | 현황 |
|------|------|
| 제재 규모 | 누적 100만+ 건, 하루 ~13,000건 |
| 주요 제재 대상 | 매크로, 작업장, 비인가 프로그램, 시스템 악용 |
| 법적 조치 | 매크로 사용자 12명+ 업무방해 형사 고소 |
| OCR 미터기 제재 | **직접 사례 미확인** |
| 안티치트 | 프로세스 감지 + HWID 차단 + 기기등록 + 서버측 탐지 |
| 화면캡처 감지 | **미확인 (감지 안 하는 것으로 추정)** |
| 공식 딜미터 | 2025.12.23 개발 중 발표, 출시 미정 |

**유사 게임 패턴:**
- WoW: 공식 Addon API → 딜미터 공식 지원
- FF14: "외부 툴 금지" 공식 입장이지만 사실상 묵인 (타인 딜 지적만 제재)
- 로스트아크: 사설 미터기 제재 → 유저 반발 → 공식 전투분석기 도입
- **아이온2: 로아 패턴 추종 중 (비공식→공식 도입 진행 중)**

### 1.6 오버레이 기술

| 방식 | 안전성 | 전체화면 | 구현 난이도 |
|------|--------|---------|-----------|
| **PyQt6 투명 윈도우** | 최고 (DLL 무주입) | 창모드/보더리스만 | 중간 |
| Tkinter 투명 윈도우 | 최고 | 창모드/보더리스만 | 쉬움 |
| DirectX Hook (goverlay) | 위험 (DLL 주입) | 전체 지원 | 어려움 |
| Electron transparent | 높음 | 창모드/보더리스 | 쉬움 |

---

## 2. 아키텍처 결정

### 2.1 접근 방식: OCR 기반 (안전 우선)

**선택 이유:**
1. 패킷 미터기는 이미 존재 → 동일 방식은 차별화 불가
2. OCR 방식의 **법적/운영 리스크 최소화**가 최대 강점
3. 공식 딜미터 출시 전까지 "안전한 대안"으로 포지셔닝
4. 공식 딜미터 이후에도 "리포트/분석/코칭" 부가가치로 존속

### 2.2 기술 스택

```
Python 3.12+
├── 캡처: mss (기본) / BetterCam (옵션)
├── OCR: winocr (기본, 빠름) / Tesseract (폴백, 검증됨)
├── 이미지 전처리: OpenCV + NumPy
├── 파싱: regex (검증된 한/영 패턴)
├── UI/오버레이: PyQt6 (투명 윈도우, 클릭 투과)
├── 시각화: PyQt6 Charts / matplotlib
├── 설정: TOML (pyproject.toml 통합)
└── 패키징: PyInstaller / Nuitka
```

### 2.3 파이프라인 아키텍처

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐
│ ScreenCapture│────>│ Preprocessor │────>│ OCR Engine │
│ (mss/Better) │     │ (crop,upscale│     │(winocr/    │
│ 10 FPS       │     │  color mask) │     │ tesseract) │
└─────────────┘     └──────────────┘     └────────────┘
                                                │
                    ┌──────────────┐     ┌──────┴──────┐
                    │  DPS Calc    │<────│ CombatParser│
                    │ (실시간 집계) │     │(regex 파싱)  │
                    └──────┬───────┘     └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Overlay  │ │ Session  │ │  Report  │
        │ (PyQt6)  │ │ Storage  │ │ (분석)   │
        └──────────┘ └──────────┘ └──────────┘
```

### 2.4 성능 목표

| 지표 | 목표 | 근거 |
|------|------|------|
| OCR 처리 | < 100ms/프레임 | winocr ~48ms, Tesseract ~1000ms (최적화 시 ~200ms) |
| 전체 파이프라인 | < 300ms | 캡처(30ms) + 전처리(20ms) + OCR(100ms) + 파싱(5ms) |
| DPS 갱신 주기 | 3~10 FPS | 전투 로그 텍스트 변경 빈도에 맞춤 |
| CPU 사용률 | < 10% | 메인 게임 성능 영향 최소화 |
| 메모리 사용 | < 200MB | PyQt6 + OCR 모델 포함 |

---

## 3. 기존 프로젝트 대비 차별화

| 항목 | ProjackL2 (기존) | 우리 프로젝트 |
|------|-----------------|-------------|
| OCR 엔진 | Tesseract 단일 | **듀얼: winocr(빠름) + Tesseract(폴백)** |
| UI | matplotlib 별도 창 | **PyQt6 투명 오버레이 (게임 위 표시)** |
| ROI 설정 | config.ini 수동 입력 | **드래그 선택 UI + 자동 감지** |
| 분석 | DPS만 표시 | **스킬별 기여도, 세션 리포트, 성능 추적** |
| 저장 | 로그만 | **세션 저장/내보내기 (JSON/CSV)** |
| 패키징 | 소스코드 실행 | **exe 배포 (PyInstaller)** |

---

## 4. 구현 로드맵

### Phase 1: MVP (2-3주)
- [ ] 프로젝트 구조 셋업 (pyproject.toml, 의존성)
- [ ] 화면 캡처 모듈 (mss, ROI 설정)
- [ ] OCR 엔진 래퍼 (winocr + Tesseract)
- [ ] 이미지 전처리 (업스케일, 색상 마스크)
- [ ] 전투 로그 파서 (검증된 한국어 정규식)
- [ ] DPS 계산기 (실시간 집계)
- [ ] 기본 콘솔 출력 (DPS 수치)

### Phase 2: UI & 오버레이 (2주)
- [ ] PyQt6 투명 오버레이 (DPS 표시)
- [ ] ROI 선택 UI (드래그 앤 드롭)
- [ ] 설정 GUI (OCR 엔진 선택, FPS 등)
- [ ] 전투 시작/종료 자동 감지
- [ ] 시스템 트레이 아이콘

### Phase 3: 분석 & 리포트 (2주)
- [ ] 세션 기록 (SQLite)
- [ ] 스킬별 기여도 분석
- [ ] 전투 세션 리포트 (차트)
- [ ] 세션 비교 (이전 세션 대비 성능)
- [ ] JSON/CSV 내보내기

### Phase 4: 배포 & 최적화 (1-2주)
- [ ] PyInstaller exe 빌드
- [ ] 자동 업데이트
- [ ] CPU/메모리 최적화
- [ ] 에러 핸들링 & 로깅

---

## 5. 리스크 & 완화

| 리스크 | 확률 | 영향 | 완화 |
|--------|------|------|------|
| 공식 딜미터 출시로 수요 감소 | 높음 | 중간 | 리포트/코칭으로 차별화 |
| 패킷 암호화로 패킷 미터 무력화 | 중간 | 해당없음 | OCR 방식이라 무관 |
| UI 업데이트로 OCR 깨짐 | 중간 | 높음 | 색상 마스크 설정 가능하게, A/B 테스트 |
| 안티치트 화면캡처 감지 | 낮음 | 높음 | OS 레벨 스크린샷만 사용, 게임 프로세스 미접근 |
| 운영정책 "비인가 프로그램" 해당 | 낮음 | 높음 | 읽기 전용, 자동화 기능 배제, 면책 고지 |

---

## 6. 출처 (Sources)

### 오픈소스 프로젝트
- [ProjackL2/aion2_dps_meter](https://github.com/ProjackL2/aion2_dps_meter) - Python OCR 기반
- [TK-open-public/Aion2-Dps-Meter](https://github.com/TK-open-public/Aion2-Dps-Meter) - Kotlin 패킷 기반
- [taengu/Aion2-Dps-Meter](https://github.com/taengu/Aion2-Dps-Meter) - Kotlin 패킷 기반

### OCR 벤치마크
- [IJACSA Vol.16 No.1 - OCR 비교 논문](https://thesai.org/Downloads/Volume16No1/Paper_44-Performance_Evaluation_of_Efficient_and_Accurate_Text_Detection.pdf)
- [winocr (GitHub)](https://github.com/GitHub30/winocr) - Windows OCR Python 래퍼
- [PaddleOCR PP-OCRv5](https://github.com/PaddlePaddle/PaddleOCR) - 한국어 전용 모델
- [IntuitionLabs - OCR 엔진 분석](https://intuitionlabs.ai/articles/non-llm-ocr-technologies)

### 화면 캡처
- [BetterCam (GitHub)](https://github.com/RootKit-Org/BetterCam) - 고성능 캡처
- [DXcam (GitHub)](https://github.com/ra1nty/DXcam)
- [screen-ocr (PyPI)](https://pypi.org/project/screen-ocr/)

### 운영정책 & 제재
- [아이온2 제재 100만건 (전자신문)](https://www.etnews.com/20260130000259)
- [아이온2 형사 고소 (디일렉)](https://www.thelec.kr/news/articleView.html?idxno=45361)
- [아이온2 딜미터기 공식화 (게임톡)](https://www.gametoc.co.kr/news/articleView.html?idxno=105046)

### 유사 게임 비교
- [ACT (GitHub)](https://github.com/EQAditu/AdvancedCombatTracker)
- [IINACT](https://www.iinact.com/)
- [딜미터기 나무위키](https://namu.wiki/w/%EB%94%9C%EB%AF%B8%ED%84%B0%EA%B8%B0)
- [로스트아크 딜미터 논쟁 (나무위키)](https://namu.wiki/w/%EB%A1%9C%EC%8A%A4%ED%8A%B8%EC%95%84%ED%81%AC%EC%9D%98%20%EB%94%9C%EB%AF%B8%ED%84%B0%EA%B8%B0%20%EB%8F%84%EC%9E%85%20%EB%85%BC%EC%9F%81)

### 오버레이
- [goverlay (GitHub)](https://github.com/hiitiger/goverlay)
- [game-overlay-sdk (PyPI)](https://pypi.org/project/game-overlay-sdk/)
