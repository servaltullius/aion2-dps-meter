"""DPS 오버레이 위젯."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from aion2meter.models import DpsSnapshot
from aion2meter.ui.sparkline import SparklineWidget

_GREEN = QColor(0, 255, 100)
_GRAY = QColor(150, 150, 150)
_BG = QColor(0, 0, 0, 180)
_SKILL_YELLOW = QColor(255, 220, 100)

_BASE_WIDTH = 220
_BASE_HEIGHT = 120
_BREAKDOWN_HEIGHT = 140  # 스파크라인(40) + 스킬(100)
_MAX_SKILLS = 5


class DpsOverlay(QWidget):
    """투명 DPS 오버레이."""

    def __init__(self, opacity: float = 0.75, bg_color: tuple[int, int, int] = (0, 0, 0)) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_BASE_WIDTH, _BASE_HEIGHT)

        self._opacity = opacity
        self._bg_color = QColor(*bg_color)
        self._combat_active = False
        self._breakdown_visible = False

        font = QFont("Consolas", 11)
        font_small = QFont("Consolas", 9)
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

        # 스파크라인
        self._sparkline = SparklineWidget(self)
        self._sparkline.setVisible(False)
        layout.addWidget(self._sparkline)

        # 스킬 breakdown 라벨들 (상위 5개)
        self._skill_labels: list[QLabel] = []
        for _ in range(_MAX_SKILLS):
            lbl = QLabel("")
            lbl.setFont(font_small)
            lbl.setStyleSheet(f"color: {_SKILL_YELLOW.name()};")
            lbl.setVisible(False)
            layout.addWidget(lbl)
            self._skill_labels.append(lbl)

        # 마우스 드래그 지원
        self._drag_pos = None

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(self._bg_color)
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

        # 스파크라인 갱신
        if self._breakdown_visible and snapshot.dps_timeline:
            self._sparkline.update_data(snapshot.dps_timeline)
            self._sparkline.setVisible(True)
        elif not self._breakdown_visible:
            self._sparkline.setVisible(False)

        # 스킬 breakdown 갱신
        if self._breakdown_visible and snapshot.skill_breakdown:
            sorted_skills = sorted(
                snapshot.skill_breakdown.items(), key=lambda x: x[1], reverse=True
            )[:_MAX_SKILLS]
            total = snapshot.total_damage or 1
            for i, lbl in enumerate(self._skill_labels):
                if i < len(sorted_skills):
                    name, dmg = sorted_skills[i]
                    pct = dmg / total * 100
                    lbl.setText(f"  {name}: {dmg:,} ({pct:.1f}%)")
                    lbl.setVisible(True)
                else:
                    lbl.setText("")
                    lbl.setVisible(False)
        else:
            for lbl in self._skill_labels:
                lbl.setVisible(False)

    def toggle_breakdown(self) -> None:
        """스킬 breakdown + 스파크라인 표시/숨기기 토글."""
        self._breakdown_visible = not self._breakdown_visible
        if self._breakdown_visible:
            self.setFixedSize(_BASE_WIDTH, _BASE_HEIGHT + _BREAKDOWN_HEIGHT)
            self._sparkline.setVisible(True)
        else:
            for lbl in self._skill_labels:
                lbl.setVisible(False)
            self._sparkline.setVisible(False)
            self.setFixedSize(_BASE_WIDTH, _BASE_HEIGHT)

    @property
    def breakdown_visible(self) -> bool:
        return self._breakdown_visible

    def set_bg_color(self, r: int, g: int, b: int) -> None:
        """배경색 변경."""
        self._bg_color = QColor(r, g, b)
        self.update()

    def mousePressEvent(self, event: object) -> None:
        if hasattr(event, "globalPosition"):
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: object) -> None:
        if self._drag_pos is not None and hasattr(event, "globalPosition"):
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: object) -> None:
        self._drag_pos = None
