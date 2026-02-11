"""앱 메인 엔트리포인트."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from aion2meter.alert_manager import AlertManager
from aion2meter.config import ConfigManager
from aion2meter.logging_config import setup_logging
from aion2meter.io.combat_logger import CombatLogExporter
from aion2meter.io.discord_notifier import DiscordNotifier
from aion2meter.models import AppConfig, DpsSnapshot, ROI
from aion2meter.pipeline.pipeline import DpsPipeline
from aion2meter.profile_manager import ProfileManager
from aion2meter.ui.overlay import DpsOverlay
from aion2meter.ui.roi_selector import RoiSelector
from aion2meter.ui.settings_dialog import SettingsDialog
from aion2meter.ui.tag_input_dialog import TagInputDialog
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

        # 알림 매니저
        self._alert_mgr = AlertManager(
            threshold=self._config.dps_alert_threshold,
            cooldown=self._config.dps_alert_cooldown,
        )

        # 프로파일 매니저
        self._profile_mgr = ProfileManager()
        self._tray.switch_profile.connect(self._switch_profile)
        self._tray.save_profile.connect(self._save_profile)
        self._update_profile_menu()

        self._roi_selector: RoiSelector | None = None
        self._settings_dialog: SettingsDialog | None = None
        self._tag_dialog: TagInputDialog | None = None
        self._pending_events: list = []
        self._pending_snapshot: object = None

        # 저장된 ROI가 있으면 바로 시작
        if self._config.roi is not None:
            self._pipeline.start(self._config.roi)

    def _on_dps_updated(self, snapshot: DpsSnapshot) -> None:
        self._overlay.update_display(snapshot)
        # DPS 알림 체크
        alert = self._alert_mgr.check(snapshot)
        if alert:
            msg = (
                f"DPS {alert.current_dps:,.0f} — 임계값 {alert.threshold:,.0f} "
                f"{'초과' if alert.alert_type == 'above' else '미달'}"
            )
            self._tray.showMessage("DPS 알림", msg)

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

        # AlertManager 재생성
        self._alert_mgr = AlertManager(
            threshold=config.dps_alert_threshold,
            cooldown=config.dps_alert_cooldown,
        )

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
        """전투 종료(자동/수동 리셋) 시 태그 입력 후 세션을 저장한다."""
        if not events:
            return
        self._pending_events = events
        self._pending_snapshot = snapshot
        self._tag_dialog = TagInputDialog()
        self._tag_dialog.tag_submitted.connect(self._finish_combat_save)
        self._tag_dialog.show()

    def _finish_combat_save(self, tag: str) -> None:
        """태그 입력 완료 후 세션 저장 + Discord 전송."""
        events = self._pending_events
        snapshot = self._pending_snapshot
        self._session_repo.save_session(events, snapshot, tag=tag)

        # Discord 자동 전송
        if self._config.discord_auto_send and self._config.discord_webhook_url:
            import threading

            threading.Thread(
                target=DiscordNotifier.send_session_summary,
                args=(snapshot, tag, self._config.discord_webhook_url),
                daemon=True,
            ).start()

    def _switch_profile(self, name: str) -> None:
        """프로파일을 전환하고 파이프라인을 재시작한다."""
        config = self._profile_mgr.switch_profile(name)
        self._config.roi = config.roi
        self._config.ocr_engine = config.ocr_engine
        self._config.idle_timeout = config.idle_timeout
        self._config_manager.save(self._config)
        # 파이프라인 재시작
        self._pipeline.stop()
        self._pipeline = DpsPipeline(config=self._config)
        self._pipeline.dps_updated.connect(self._on_dps_updated)
        self._pipeline._calculator.set_on_reset(self._on_combat_ended)
        if self._config.roi is not None:
            self._pipeline.start(self._config.roi)
        self._update_profile_menu()

    def _save_profile(self) -> None:
        """현재 설정을 프로파일로 저장한다."""
        from PyQt6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(None, "프로파일 저장", "프로파일 이름:")
        if ok and name.strip():
            self._profile_mgr.save_current_as(name.strip(), self._config)
            self._update_profile_menu()

    def _update_profile_menu(self) -> None:
        """트레이의 프로파일 메뉴를 갱신한다."""
        names = self._profile_mgr.list_profiles()
        active = self._profile_mgr.get_active()
        self._tray.update_profile_menu(names, active)

    def _open_sessions(self) -> None:
        dlg = SessionListDialog(self._session_repo)
        dlg.exec()

    def _quit(self) -> None:
        # 오버레이 위치 저장
        pos = self._overlay.pos()
        self._config.overlay_x = pos.x()
        self._config.overlay_y = pos.y()
        self._config_manager.save(self._config)

        # 활성 세션 저장 (태그 없이)
        events = self._pipeline.get_event_history()
        if events:
            snapshot = self._pipeline._calculator.add_events([])
            self._session_repo.save_session(events, snapshot, tag="")

        self._hotkey_mgr.stop()
        self._pipeline.stop()
        self._app.quit()

    def run(self) -> int:
        return self._app.exec()


def main() -> None:
    app = App()
    sys.exit(app.run())
