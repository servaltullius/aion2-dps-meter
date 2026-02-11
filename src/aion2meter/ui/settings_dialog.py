"""설정 다이얼로그."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt

from aion2meter.models import AppConfig


class SettingsDialog(QDialog):
    """오버레이 설정 다이얼로그."""

    settings_changed = pyqtSignal(AppConfig)

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.setMinimumWidth(300)
        self._config = config

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 투명도 슬라이더 (0~100 → 0.0~1.0)
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(10, 100)
        self._opacity_slider.setValue(int(config.overlay_opacity * 100))
        self._opacity_label = QLabel(f"{config.overlay_opacity:.0%}")
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_label.setText(f"{v}%")
        )
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self._opacity_slider)
        opacity_row.addWidget(self._opacity_label)
        form.addRow("투명도:", opacity_row)

        # 크기 스핀박스
        self._width_spin = QSpinBox()
        self._width_spin.setRange(150, 600)
        self._width_spin.setValue(config.overlay_width)
        form.addRow("너비:", self._width_spin)

        self._height_spin = QSpinBox()
        self._height_spin.setRange(80, 400)
        self._height_spin.setValue(config.overlay_height)
        form.addRow("높이:", self._height_spin)

        # 배경색 선택
        self._bg_color = QColor(*config.overlay_bg_color)
        self._color_btn = QPushButton()
        self._update_color_btn()
        self._color_btn.clicked.connect(self._pick_color)
        form.addRow("배경색:", self._color_btn)

        # 단축키 설정
        self._hotkey_overlay_edit = QLineEdit(config.hotkey_overlay)
        form.addRow("오버레이 단축키:", self._hotkey_overlay_edit)

        self._hotkey_reset_edit = QLineEdit(config.hotkey_reset)
        form.addRow("전투 초기화 단축키:", self._hotkey_reset_edit)

        self._hotkey_breakdown_edit = QLineEdit(config.hotkey_breakdown)
        form.addRow("스킬 상세 단축키:", self._hotkey_breakdown_edit)

        # 자동 업데이트
        self._auto_update_check = QCheckBox("자동 업데이트 확인")
        self._auto_update_check.setChecked(config.auto_update_check)
        form.addRow("", self._auto_update_check)

        layout.addLayout(form)

        # 확인/취소 버튼
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("확인")
        ok_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _update_color_btn(self) -> None:
        self._color_btn.setStyleSheet(
            f"background-color: {self._bg_color.name()}; min-width: 60px; min-height: 24px;"
        )
        self._color_btn.setText(self._bg_color.name())

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(self._bg_color, self, "배경색 선택")
        if color.isValid():
            self._bg_color = color
            self._update_color_btn()

    def _apply(self) -> None:
        self._config.overlay_opacity = self._opacity_slider.value() / 100.0
        self._config.overlay_width = self._width_spin.value()
        self._config.overlay_height = self._height_spin.value()
        self._config.overlay_bg_color = (
            self._bg_color.red(),
            self._bg_color.green(),
            self._bg_color.blue(),
        )
        self._config.hotkey_overlay = self._hotkey_overlay_edit.text()
        self._config.hotkey_reset = self._hotkey_reset_edit.text()
        self._config.hotkey_breakdown = self._hotkey_breakdown_edit.text()
        self._config.auto_update_check = self._auto_update_check.isChecked()
        self.settings_changed.emit(self._config)
        self.accept()
