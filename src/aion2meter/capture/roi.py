"""ROI 유효성 검증."""

from __future__ import annotations

from aion2meter.models import ROI


def validate_roi(roi: ROI, screen_width: int, screen_height: int) -> bool:
    """ROI가 화면 범위 내에 있는지 확인한다."""
    if roi.left + roi.width > screen_width:
        return False
    if roi.top + roi.height > screen_height:
        return False
    return True
