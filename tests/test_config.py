"""설정 관리 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from aion2meter.config import ConfigManager
from aion2meter.models import AppConfig, ColorRange, ROI


@pytest.fixture()
def manager(tmp_path: Path) -> ConfigManager:
    return ConfigManager(default_path=tmp_path / "config.toml")


class TestConfigLoad:
    """로드 테스트."""

    def test_default_when_file_missing(self, manager: ConfigManager) -> None:
        """파일이 없으면 기본값을 반환한다."""
        cfg = manager.load()
        assert cfg.fps == 10
        assert cfg.ocr_engine == "winocr"
        assert cfg.idle_timeout == 5.0
        assert cfg.overlay_opacity == 0.75
        assert cfg.overlay_width == 220
        assert cfg.overlay_height == 120
        assert cfg.overlay_x is None
        assert cfg.overlay_y is None
        assert cfg.overlay_bg_color == (0, 0, 0)
        assert cfg.roi is None
        assert len(cfg.color_ranges) == 5

    def test_load_from_toml(self, tmp_path: Path) -> None:
        """TOML 파일에서 설정을 올바르게 읽는다."""
        toml_content = """\
fps = 30
ocr_engine = "tesseract"
idle_timeout = 10.0
overlay_opacity = 0.5

[roi]
left = 100
top = 200
width = 800
height = 600

[[color_ranges]]
name = "white"
lower = [182, 144, 100]
upper = [255, 200, 140]
"""
        config_path = tmp_path / "custom.toml"
        config_path.write_text(toml_content, encoding="utf-8")

        mgr = ConfigManager()
        cfg = mgr.load(path=config_path)

        assert cfg.fps == 30
        assert cfg.ocr_engine == "tesseract"
        assert cfg.idle_timeout == 10.0
        assert cfg.overlay_opacity == 0.5
        assert cfg.roi is not None
        assert cfg.roi.left == 100
        assert cfg.roi.width == 800
        assert len(cfg.color_ranges) == 1
        assert cfg.color_ranges[0].name == "white"

    def test_load_without_color_ranges_uses_defaults(self, tmp_path: Path) -> None:
        """color_ranges가 없으면 기본 색상 범위를 사용한다."""
        toml_content = """\
fps = 10
ocr_engine = "winocr"
idle_timeout = 5.0
overlay_opacity = 0.75
"""
        config_path = tmp_path / "no_colors.toml"
        config_path.write_text(toml_content, encoding="utf-8")

        mgr = ConfigManager()
        cfg = mgr.load(path=config_path)
        assert len(cfg.color_ranges) == 5


class TestConfigSave:
    """저장 테스트."""

    def test_save_and_reload(self, manager: ConfigManager) -> None:
        """저장 후 다시 로드하면 동일한 설정을 얻는다."""
        original = AppConfig(
            roi=ROI(left=10, top=20, width=300, height=400),
            fps=15,
            ocr_engine="tesseract",
            idle_timeout=3.0,
            overlay_opacity=0.9,
            color_ranges=[
                ColorRange("red", (0, 0, 180), (80, 80, 255)),
            ],
        )
        manager.save(original)
        loaded = manager.load()

        assert loaded.fps == original.fps
        assert loaded.ocr_engine == original.ocr_engine
        assert loaded.idle_timeout == original.idle_timeout
        assert loaded.overlay_opacity == original.overlay_opacity
        assert loaded.roi is not None
        assert loaded.roi.left == 10
        assert loaded.roi.width == 300
        assert len(loaded.color_ranges) == 1
        assert loaded.color_ranges[0].name == "red"

    def test_save_without_roi(self, manager: ConfigManager) -> None:
        """ROI가 None이면 TOML에 roi 섹션이 없다."""
        cfg = AppConfig(
            fps=10,
            ocr_engine="winocr",
            idle_timeout=5.0,
            overlay_opacity=0.75,
            color_ranges=AppConfig.default_color_ranges(),
        )
        manager.save(cfg)

        toml_text = manager.default_path.read_text(encoding="utf-8")
        assert "[roi]" not in toml_text

        reloaded = manager.load()
        assert reloaded.roi is None

    def test_save_with_roi(self, manager: ConfigManager) -> None:
        """ROI가 있으면 TOML에 roi 섹션이 포함된다."""
        cfg = AppConfig(
            roi=ROI(left=50, top=60, width=640, height=480),
            fps=10,
            ocr_engine="winocr",
            idle_timeout=5.0,
            overlay_opacity=0.75,
            color_ranges=AppConfig.default_color_ranges(),
        )
        manager.save(cfg)

        toml_text = manager.default_path.read_text(encoding="utf-8")
        assert "[roi]" in toml_text
        assert "left = 50" in toml_text

        reloaded = manager.load()
        assert reloaded.roi is not None
        assert reloaded.roi.left == 50

    def test_save_and_reload_overlay_fields(self, manager: ConfigManager) -> None:
        """오버레이 확장 필드가 저장/로드된다."""
        cfg = AppConfig(
            overlay_width=300,
            overlay_height=200,
            overlay_x=100,
            overlay_y=50,
            overlay_bg_color=(30, 30, 60),
            color_ranges=AppConfig.default_color_ranges(),
        )
        manager.save(cfg)
        loaded = manager.load()
        assert loaded.overlay_width == 300
        assert loaded.overlay_height == 200
        assert loaded.overlay_x == 100
        assert loaded.overlay_y == 50
        assert loaded.overlay_bg_color == (30, 30, 60)

    def test_save_overlay_without_position(self, manager: ConfigManager) -> None:
        """overlay_x/y가 None이면 TOML에 포함되지 않는다."""
        cfg = AppConfig(color_ranges=AppConfig.default_color_ranges())
        manager.save(cfg)
        toml_text = manager.default_path.read_text(encoding="utf-8")
        assert "overlay_x" not in toml_text
        assert "overlay_y" not in toml_text


class TestHotkeyConfig:
    """핫키 설정 직렬화/역직렬화."""

    def test_default_hotkeys(self):
        config = AppConfig()
        assert config.hotkey_overlay == "<ctrl>+<shift>+o"
        assert config.hotkey_reset == "<ctrl>+<shift>+r"
        assert config.hotkey_breakdown == "<ctrl>+<shift>+b"

    def test_hotkey_roundtrip(self, tmp_path):
        config = AppConfig(
            hotkey_overlay="<ctrl>+<alt>+d",
            hotkey_reset="<ctrl>+<alt>+r",
            hotkey_breakdown="<ctrl>+<alt>+b",
        )
        mgr = ConfigManager(default_path=tmp_path / "config.toml")
        mgr.save(config)
        loaded = mgr.load()
        assert loaded.hotkey_overlay == "<ctrl>+<alt>+d"
        assert loaded.hotkey_reset == "<ctrl>+<alt>+r"
        assert loaded.hotkey_breakdown == "<ctrl>+<alt>+b"


class TestDiscordConfig:
    """Discord 설정 직렬화/역직렬화."""

    def test_default_discord_config(self):
        config = AppConfig()
        assert config.discord_webhook_url == ""
        assert config.discord_auto_send is False

    def test_discord_config_roundtrip(self, tmp_path):
        config = AppConfig(
            discord_webhook_url="https://discord.com/api/webhooks/123/abc",
            discord_auto_send=True,
        )
        mgr = ConfigManager(default_path=tmp_path / "config.toml")
        mgr.save(config)
        loaded = mgr.load()
        assert loaded.discord_webhook_url == "https://discord.com/api/webhooks/123/abc"
        assert loaded.discord_auto_send is True


class TestAlertConfig:
    """DPS 알림 설정 직렬화/역직렬화."""

    def test_default_alert_config(self):
        config = AppConfig()
        assert config.dps_alert_threshold == 0.0
        assert config.dps_alert_cooldown == 10.0

    def test_alert_config_roundtrip(self, tmp_path):
        config = AppConfig(dps_alert_threshold=5000.0, dps_alert_cooldown=15.0)
        mgr = ConfigManager(default_path=tmp_path / "config.toml")
        mgr.save(config)
        loaded = mgr.load()
        assert loaded.dps_alert_threshold == 5000.0
        assert loaded.dps_alert_cooldown == 15.0
