"""앱 메인 엔트리포인트."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from aion2meter.config import ConfigManager
from aion2meter.logging_config import setup_logging
from aion2meter.io.combat_logger import CombatLogExporter
from aion2meter.models import AppConfig, DpsSnapshot, ROI
from aion2meter.pipeline.pipeline import DpsPipeline
from aion2meter.ui.overlay import DpsOverlay
from aion2meter.ui.roi_selector import RoiSelector
from aion2meter.ui.settings_dialog import SettingsDialog
from aion2meter.ui.tray_icon import TrayIcon
from aion2meter.io.session_repository import SessionRepository
from aion2meter.ui.session_report import SessionListDialog
from aion2meter.hotkey_manager import HotkeyManager
from aion2meter.updater import check_for_update

_LOG_DIR = Path.home() / "Documents" / "aion2meter" / "logs"


class App:
    """앱 클래스: 설정 로드, 파이프라인↔오버레이 연결."""

    def __init__(self) -> None:
        setup_logging()
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        # 설정 로드
        self._config_manager = ConfigManager()
        self._config = self._config_manager.load()

        self._session_repo = SessionRepository()

        # 파이프라인
        self._pipeline = DpsPipeline(config=self._config)
        self._pipeline.dps_updated.connect(self._on_dps_updated)
        self._pipeline._calculator.set_on_reset(self._on_combat_ended)

        # UI
        self._overlay = DpsOverlay(
            opacity=self._config.overlay_opacity,
            bg_color=self._config.overlay_bg_color,
        )
        if self._config.overlay_x is not None and self._config.overlay_y is not None:
            self._overlay.move(self._config.overlay_x, self._config.overlay_y)
        self._overlay.show()

        self._tray = TrayIcon()
        self._tray.toggle_overlay.connect(self._toggle_overlay)
        self._tray.select_roi.connect(self._open_roi_selector)
        self._tray.reset_combat.connect(self._reset_combat)
        self._tray.toggle_breakdown.connect(self._toggle_breakdown)
        self._tray.save_log.connect(self._save_log)
        self._tray.open_settings.connect(self._open_settings)
        self._tray.quit_app.connect(self._quit)
        self._tray.open_sessions.connect(self._open_sessions)
        self._tray.show()

        # 글로벌 단축키
        self._hotkey_mgr = HotkeyManager()
        self._hotkey_mgr.register(self._config.hotkey_overlay, self._toggle_overlay)
        self._hotkey_mgr.register(self._config.hotkey_reset, self._reset_combat)
        self._hotkey_mgr.register(self._config.hotkey_breakdown, self._toggle_breakdown)
        self._hotkey_mgr.start()

        # 자동 업데이트 확인
        self._tray.check_update.connect(self._check_update)
        if self._config.auto_update_check:
            self._check_update()

        self._roi_selector: RoiSelector | None = None
        self._settings_dialog: SettingsDialog | None = None

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

    def _toggle_breakdown(self) -> None:
        self._overlay.toggle_breakdown()

    def _save_log(self) -> None:
        events = self._pipeline.get_event_history()
        if not events:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        CombatLogExporter.export_csv(events, _LOG_DIR / f"combat_{ts}.csv")
        CombatLogExporter.export_json(events, _LOG_DIR / f"combat_{ts}.json")

    def _open_settings(self) -> None:
        self._settings_dialog = SettingsDialog(self._config)
        self._settings_dialog.settings_changed.connect(self._on_settings_changed)
        self._settings_dialog.show()

    def _on_settings_changed(self, config: AppConfig) -> None:
        self._config = config
        self._overlay._opacity = config.overlay_opacity
        self._overlay.set_bg_color(*config.overlay_bg_color)
        self._config_manager.save(self._config)

        # 핫키 재등록
        self._hotkey_mgr.stop()
        self._hotkey_mgr.unregister_all()
        self._hotkey_mgr.register(config.hotkey_overlay, self._toggle_overlay)
        self._hotkey_mgr.register(config.hotkey_reset, self._reset_combat)
        self._hotkey_mgr.register(config.hotkey_breakdown, self._toggle_breakdown)
        self._hotkey_mgr.start()

    def _check_update(self) -> None:
        """GitHub에서 최신 버전을 확인한다."""
        import threading

        def _check():
            result = check_for_update("0.1.0")
            if result:
                version, url = result
                self._tray.showMessage(
                    "업데이트 알림",
                    f"새 버전 {version}이 있습니다.\n{url}",
                )

        threading.Thread(target=_check, daemon=True).start()

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

    def _on_combat_ended(self, events: list, snapshot: object) -> None:
        """전투 종료(자동/수동 리셋) 시 세션을 저장한다."""
        if events:
            self._session_repo.save_session(events, snapshot)

    def _open_sessions(self) -> None:
        dlg = SessionListDialog(self._session_repo)
        dlg.exec()

    def _quit(self) -> None:
        # 오버레이 위치 저장
        pos = self._overlay.pos()
        self._config.overlay_x = pos.x()
        self._config.overlay_y = pos.y()
        self._config_manager.save(self._config)

        # 활성 세션 저장
        events = self._pipeline.get_event_history()
        if events:
            snapshot = self._pipeline._calculator.add_events([])
            self._session_repo.save_session(events, snapshot)

        self._hotkey_mgr.stop()
        self._pipeline.stop()
        self._app.quit()

    def run(self) -> int:
        return self._app.exec()


def main() -> None:
    app = App()
    sys.exit(app.run())
