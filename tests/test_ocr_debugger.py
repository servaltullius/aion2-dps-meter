"""OCR 디버그 도구 단위 테스트."""

from __future__ import annotations

import json

import numpy as np
import pytest

from aion2meter.models import DamageEvent, HitType


class TestOcrDebugger:
    """OcrDebugger 테스트."""

    def test_dump_creates_files(self, tmp_path) -> None:
        """enabled=True이면 프레임 디렉토리와 파일들을 생성한다."""
        from aion2meter.io.ocr_debugger import OcrDebugger

        debugger = OcrDebugger(output_dir=tmp_path / "debug", enabled=True)
        raw = np.zeros((10, 20, 3), dtype=np.uint8)
        processed = np.zeros((20, 40), dtype=np.uint8)
        ocr_text = "테스트 텍스트"
        events = [
            DamageEvent(timestamp=1.0, source="", target="몬스터", skill="검격", damage=100, hit_type=HitType.NORMAL),
        ]

        debugger.dump(raw, processed, ocr_text, events)

        frame_dir = tmp_path / "debug" / "frame_000001"
        assert frame_dir.exists()
        assert (frame_dir / "raw.png").exists()
        assert (frame_dir / "processed.png").exists()
        assert (frame_dir / "ocr.txt").read_text(encoding="utf-8") == "테스트 텍스트"
        events_data = json.loads((frame_dir / "events.json").read_text(encoding="utf-8"))
        assert len(events_data) == 1
        assert events_data[0]["damage"] == 100

    def test_dump_disabled_creates_nothing(self, tmp_path) -> None:
        """enabled=False이면 아무 파일도 생성하지 않는다."""
        from aion2meter.io.ocr_debugger import OcrDebugger

        debugger = OcrDebugger(output_dir=tmp_path / "debug", enabled=False)
        raw = np.zeros((10, 20, 3), dtype=np.uint8)
        processed = np.zeros((20, 40), dtype=np.uint8)

        debugger.dump(raw, processed, "text", [])

        assert not (tmp_path / "debug").exists()

    def test_dump_increments_counter(self, tmp_path) -> None:
        """dump()를 여러 번 호출하면 카운터가 증가한다."""
        from aion2meter.io.ocr_debugger import OcrDebugger

        debugger = OcrDebugger(output_dir=tmp_path / "debug", enabled=True)
        raw = np.zeros((10, 20, 3), dtype=np.uint8)
        processed = np.zeros((20, 40), dtype=np.uint8)

        debugger.dump(raw, processed, "1", [])
        debugger.dump(raw, processed, "2", [])

        assert (tmp_path / "debug" / "frame_000001").exists()
        assert (tmp_path / "debug" / "frame_000002").exists()

    def test_dump_with_empty_events(self, tmp_path) -> None:
        """이벤트가 비어있어도 정상 동작한다."""
        from aion2meter.io.ocr_debugger import OcrDebugger

        debugger = OcrDebugger(output_dir=tmp_path / "debug", enabled=True)
        raw = np.zeros((10, 20, 3), dtype=np.uint8)
        processed = np.zeros((20, 40), dtype=np.uint8)

        debugger.dump(raw, processed, "", [])

        frame_dir = tmp_path / "debug" / "frame_000001"
        events_data = json.loads((frame_dir / "events.json").read_text(encoding="utf-8"))
        assert events_data == []
