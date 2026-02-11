"""앱 메인 엔트리포인트."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from aion2meter.config import ConfigManager
from aion2meter.models import AppConfig, DpsSnapshot, ROI
from aion2meter.pipeline.pipeline import DpsPipeline
from aion2meter.ui.overlay import DpsOverlay
from aion2meter.ui.roi_selector import RoiSelector
from aion2meter.ui.tray_icon import TrayIcon


class App:
    """앱 클래스: 설정 로드, 파이프라인↔오버레이 연결."""

    def __init__(self) -> None:
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        # 설정 로드
        self._config_manager = ConfigManager()
        self._config = self._config_manager.load()

        # 파이프라인
        self._pipeline = DpsPipeline(config=self._config)
        self._pipeline.dps_updated.connect(self._on_dps_updated)

        # UI
        self._overlay = DpsOverlay(opacity=self._config.overlay_opacity)
        self._overlay.show()

        self._tray = TrayIcon()
        self._tray.toggle_overlay.connect(self._toggle_overlay)
        self._tray.select_roi.connect(self._open_roi_selector)
        self._tray.reset_combat.connect(self._reset_combat)
        self._tray.quit_app.connect(self._quit)
        self._tray.show()

        self._roi_selector: RoiSelector | None = None

        # 저장된 ROI가 있으면 바로 시작
        if self._config.roi is not None:
            self._pipeline.start(self._config.roi)

    def _on_dps_updated(self, snapshot: DpsSnapshot) -> None:
        self._overlay.update_display(snapshot)

    def _toggle_overlay(self) -> None:
        if self._overlay.isVisible():
            self._overlay.hide()
        else:
            self._overlay.show()

    def _open_roi_selector(self) -> None:
        self._pipeline.stop()
        self._roi_selector = RoiSelector()
        self._roi_selector.roi_selected.connect(self._on_roi_selected)
        self._roi_selector.show()

    def _on_roi_selected(self, roi: ROI) -> None:
        self._config.roi = roi
        self._config_manager.save(self._config)
        self._pipeline.start(roi)

    def _reset_combat(self) -> None:
        self._pipeline.reset_combat()

    def _quit(self) -> None:
        self._pipeline.stop()
        self._app.quit()

    def run(self) -> int:
        return self._app.exec()


def main() -> None:
    app = App()
    sys.exit(app.run())
