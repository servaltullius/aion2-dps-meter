"""OCR 디버그 프레임 덤프."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from aion2meter.models import DamageEvent


class OcrDebugger:
    """OCR 파이프라인 결과를 프레임별로 파일에 덤프한다."""

    def __init__(self, output_dir: Path, enabled: bool = False) -> None:
        self._output_dir = output_dir
        self._enabled = enabled
        self._counter = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def dump(
        self,
        raw_frame: np.ndarray,
        processed_image: np.ndarray,
        ocr_text: str,
        parsed_events: list[DamageEvent],
    ) -> None:
        """한 프레임의 전체 파이프라인 결과를 저장한다."""
        if not self._enabled:
            return

        self._counter += 1
        frame_dir = self._output_dir / f"frame_{self._counter:06d}"
        frame_dir.mkdir(parents=True, exist_ok=True)

        cv2.imwrite(str(frame_dir / "raw.png"), raw_frame)
        cv2.imwrite(str(frame_dir / "processed.png"), processed_image)
        (frame_dir / "ocr.txt").write_text(ocr_text, encoding="utf-8")

        events_data = []
        for e in parsed_events:
            d = asdict(e)
            d["hit_type"] = e.hit_type.value
            events_data.append(d)

        (frame_dir / "events.json").write_text(
            json.dumps(events_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
