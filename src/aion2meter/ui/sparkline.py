"""실시간 DPS 스파크라인 위젯."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

_LINE_COLOR = QColor(0, 255, 100)
_GRID_COLOR = QColor(255, 255, 255, 30)


class SparklineWidget(QWidget):
    """QPainter 기반 경량 스파크라인 차트."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(200, 40)
        self._data: list[tuple[float, float]] = []

    def update_data(self, timeline: list[tuple[float, float]]) -> None:
        """타임라인 데이터를 갱신한다. (elapsed, dps) 튜플 리스트."""
        self._data = timeline
        self.update()

    def paintEvent(self, event: object) -> None:
        if len(self._data) < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 2

        # 그리드 (수평 반선)
        painter.setPen(QPen(_GRID_COLOR, 1))
        painter.drawLine(margin, h // 2, w - margin, h // 2)

        # Y축 스케일
        max_dps = max(d for _, d in self._data)
        if max_dps <= 0:
            painter.end()
            return

        # 라인 패스
        path = QPainterPath()
        data_w = w - 2 * margin
        data_h = h - 2 * margin
        n = len(self._data)

        for i, (_, dps) in enumerate(self._data):
            x = margin + (i / max(n - 1, 1)) * data_w
            y = margin + data_h - (dps / max_dps) * data_h
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        painter.setPen(QPen(_LINE_COLOR, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()
