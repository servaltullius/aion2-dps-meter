"""시스템 트레이 아이콘."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget


def _create_default_icon() -> QIcon:
    """기본 아이콘 생성 (간단한 색상 사각형)."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setBrush(QColor(0, 200, 100))
    painter.setPen(QColor(0, 200, 100))
    painter.drawRoundedRect(2, 2, 28, 28, 4, 4)
    painter.setPen(QColor(255, 255, 255))
    from PyQt6.QtGui import QFont
    font = QFont("Arial", 14, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), 0x0084, "D")  # AlignCenter
    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    """시스템 트레이 아이콘."""

    toggle_overlay = pyqtSignal()
    select_roi = pyqtSignal()
    reset_combat = pyqtSignal()
    toggle_breakdown = pyqtSignal()
    save_log = pyqtSignal()
    open_settings = pyqtSignal()
    quit_app = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(_create_default_icon(), parent)
        self.setToolTip("아이온2 DPS 미터")

        menu = QMenu()

        toggle_action = QAction("오버레이 표시/숨기기", menu)
        toggle_action.triggered.connect(self.toggle_overlay.emit)
        menu.addAction(toggle_action)

        breakdown_action = QAction("스킬 상세", menu)
        breakdown_action.triggered.connect(self.toggle_breakdown.emit)
        menu.addAction(breakdown_action)

        roi_action = QAction("ROI 영역 설정", menu)
        roi_action.triggered.connect(self.select_roi.emit)
        menu.addAction(roi_action)

        reset_action = QAction("전투 초기화", menu)
        reset_action.triggered.connect(self.reset_combat.emit)
        menu.addAction(reset_action)

        save_log_action = QAction("전투 로그 저장", menu)
        save_log_action.triggered.connect(self.save_log.emit)
        menu.addAction(save_log_action)

        menu.addSeparator()

        settings_action = QAction("설정", menu)
        settings_action.triggered.connect(self.open_settings.emit)
        menu.addAction(settings_action)

        quit_action = QAction("종료", menu)
        quit_action.triggered.connect(self.quit_app.emit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_overlay.emit()
