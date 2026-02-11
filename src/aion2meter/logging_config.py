"""로깅 설정."""
from __future__ import annotations
import logging
from pathlib import Path

_LOG_DIR = Path.home() / ".aion2meter" / "logs"

def setup_logging(level: int = logging.INFO) -> None:
    """파일 + 콘솔 로깅을 설정한다."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(_LOG_DIR / "aion2meter.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
