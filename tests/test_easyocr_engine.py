"""EasyOCR 엔진 단위 테스트."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from aion2meter.models import OcrResult


class TestEasyOcrEngine:
    """EasyOcrEngine 테스트."""

    def test_implements_ocr_engine_protocol(self) -> None:
        """OcrEngine Protocol을 구현한다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        from aion2meter.protocols import OcrEngine
        engine = EasyOcrEngine(gpu=False)
        assert isinstance(engine, OcrEngine)

    def test_recognize_returns_ocr_result(self) -> None:
        """recognize()는 OcrResult를 반환한다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        engine = EasyOcrEngine(gpu=False)

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = [
            ([[0, 0], [100, 0], [100, 30], [0, 30]], "몬스터에게 검격을 사용해 1,234의 대미지를 줬습니다", 0.95),
        ]
        engine._reader = mock_reader

        image = np.zeros((30, 100), dtype=np.uint8)
        result = engine.recognize(image)

        assert isinstance(result, OcrResult)
        assert "몬스터" in result.text
        assert result.confidence == pytest.approx(0.95)
        mock_reader.readtext.assert_called_once()

    def test_recognize_joins_multiple_lines(self) -> None:
        """여러 라인의 OCR 결과를 줄바꿈으로 결합한다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        engine = EasyOcrEngine(gpu=False)

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = [
            ([[0, 0], [100, 0], [100, 15], [0, 15]], "라인1", 0.90),
            ([[0, 15], [100, 15], [100, 30], [0, 30]], "라인2", 0.80),
        ]
        engine._reader = mock_reader

        image = np.zeros((30, 100), dtype=np.uint8)
        result = engine.recognize(image)

        assert result.text == "라인1\n라인2"
        assert result.confidence == pytest.approx(0.85)

    def test_recognize_empty_result(self) -> None:
        """OCR 결과가 없으면 빈 텍스트와 confidence 0을 반환한다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        engine = EasyOcrEngine(gpu=False)

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = []
        engine._reader = mock_reader

        image = np.zeros((30, 100), dtype=np.uint8)
        result = engine.recognize(image)

        assert result.text == ""
        assert result.confidence == 0.0

    def test_lazy_init_not_called_until_recognize(self) -> None:
        """EasyOCR reader는 recognize() 호출 전까지 초기화되지 않는다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        engine = EasyOcrEngine(gpu=False)
        assert engine._reader is None

    def test_import_error_raises_runtime_error(self) -> None:
        """easyocr가 설치되지 않으면 RuntimeError가 발생한다."""
        from aion2meter.ocr.easyocr_engine import EasyOcrEngine
        engine = EasyOcrEngine(gpu=False)

        # Simulate easyocr not being installed by patching the import
        import importlib
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def mock_import(name, *args, **kwargs):
            if name == "easyocr":
                raise ImportError("No module named 'easyocr'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(RuntimeError, match="easyocr"):
                engine._ensure_reader()
