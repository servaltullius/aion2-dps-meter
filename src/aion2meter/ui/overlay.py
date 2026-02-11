"""DPS 오버레이 위젯."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from aion2meter.models import DpsSnapshot

_GREEN = QColor(0, 255, 100)
_GRAY = QColor(150, 150, 150)
_BG = QColor(0, 0, 0, 180)


class DpsOverlay(QWidget):
    """투명 DPS 오버레이."""

    def __init__(self, opacity: float = 0.75) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(220, 120)

        self._opacity = opacity
        self._combat_active = False

        font = QFont("Consolas", 11)
        font_large = QFont("Consolas", 18, QFont.Weight.Bold)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self._dps_label = QLabel("DPS: 0")
        self._dps_label.setFont(font_large)
        self._dps_label.setStyleSheet(f"color: {_GRAY.name()};")

        self._total_label = QLabel("Total: 0")
        self._total_label.setFont(font)
        self._total_label.setStyleSheet("color: #cccccc;")

        self._time_label = QLabel("Time: 0.0s")
        self._time_label.setFont(font)
        self._time_label.setStyleSheet("color: #cccccc;")

        self._peak_label = QLabel("Peak: 0")
        self._peak_label.setFont(font)
        self._peak_label.setStyleSheet("color: #cccccc;")

        layout.addWidget(self._dps_label)
        layout.addWidget(self._total_label)
        layout.addWidget(self._time_label)
        layout.addWidget(self._peak_label)

        # 마우스 드래그 지원
        self._drag_pos = None

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(_BG)
        bg.setAlphaF(self._opacity)
        painter.setBrush(bg)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 8, 8)

    def update_display(self, snapshot: DpsSnapshot) -> None:
        """DPS 스냅샷으로 표시 갱신."""
        self._combat_active = snapshot.combat_active
        color = _GREEN if snapshot.combat_active else _GRAY
        self._dps_label.setText(f"DPS: {snapshot.dps:,.0f}")
        self._dps_label.setStyleSheet(f"color: {color.name()};")
        self._total_label.setText(f"Total: {snapshot.total_damage:,}")
        self._time_label.setText(f"Time: {snapshot.elapsed_seconds:.1f}s")
        self._peak_label.setText(f"Peak: {snapshot.peak_dps:,.0f}")

    def mousePressEvent(self, event: object) -> None:
        if hasattr(event, "globalPosition"):
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: object) -> None:
        if self._drag_pos is not None and hasattr(event, "globalPosition"):
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: object) -> None:
        self._drag_pos = None
