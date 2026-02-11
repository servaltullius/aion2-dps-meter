"""TOML 기반 설정 관리."""

from __future__ import annotations

import tomllib
from pathlib import Path

from aion2meter.models import AppConfig, ColorRange, PreprocessConfig, ROI

_DEFAULT_PATH = Path.home() / ".aion2meter" / "config.toml"


class ConfigManager:
    """AppConfig를 TOML 파일로 로드/저장하는 관리자."""

    def __init__(self, default_path: Path | None = None) -> None:
        self.default_path = default_path or _DEFAULT_PATH

    # ── 로드 ──────────────────────────────────────────────

    def load(self, path: Path | None = None) -> AppConfig:
        """TOML 파일에서 설정을 로드한다. 파일이 없으면 기본값을 반환."""
        target = path or self.default_path
        if not target.exists():
            return AppConfig(color_ranges=AppConfig.default_color_ranges())

        with open(target, "rb") as f:
            data = tomllib.load(f)

        roi: ROI | None = None
        if "roi" in data:
            r = data["roi"]
            roi = ROI(
                left=int(r["left"]),
                top=int(r["top"]),
                width=int(r["width"]),
                height=int(r["height"]),
            )

        color_ranges: list[ColorRange] = []
        for cr in data.get("color_ranges", []):
            color_ranges.append(
                ColorRange(
                    name=str(cr["name"]),
                    lower=tuple(cr["lower"]),  # type: ignore[arg-type]
                    upper=tuple(cr["upper"]),  # type: ignore[arg-type]
                )
            )
        if not color_ranges:
            color_ranges = AppConfig.default_color_ranges()

        # overlay 위치
        overlay_x = data.get("overlay_x")
        overlay_y = data.get("overlay_y")

        # overlay 배경색
        bg_raw = data.get("overlay_bg_color", [0, 0, 0])
        overlay_bg_color = tuple(bg_raw)  # type: ignore[arg-type]

        # preprocess 설정
        preprocess_data = data.get("preprocess", {})
        preprocess = PreprocessConfig(
            upscale_factor=int(preprocess_data.get("upscale_factor", 2)),
            denoise=bool(preprocess_data.get("denoise", True)),
            sharpen=bool(preprocess_data.get("sharpen", True)),
            adaptive_threshold=bool(preprocess_data.get("adaptive_threshold", False)),
            cleanup_min_area=int(preprocess_data.get("cleanup_min_area", 10)),
        )

        return AppConfig(
            roi=roi,
            fps=int(data.get("fps", 10)),
            ocr_engine=str(data.get("ocr_engine", "winocr")),
            ocr_fallback=str(data.get("ocr_fallback", "")),
            ocr_mode=str(data.get("ocr_mode", "failover")),
            ocr_debug=bool(data.get("ocr_debug", False)),
            idle_timeout=float(data.get("idle_timeout", 5.0)),
            overlay_opacity=float(data.get("overlay_opacity", 0.75)),
            overlay_width=int(data.get("overlay_width", 220)),
            overlay_height=int(data.get("overlay_height", 120)),
            overlay_x=int(overlay_x) if overlay_x is not None else None,
            overlay_y=int(overlay_y) if overlay_y is not None else None,
            overlay_bg_color=overlay_bg_color,
            hotkey_overlay=str(data.get("hotkey_overlay", "<ctrl>+<shift>+o")),
            hotkey_reset=str(data.get("hotkey_reset", "<ctrl>+<shift>+r")),
            hotkey_breakdown=str(data.get("hotkey_breakdown", "<ctrl>+<shift>+b")),
            auto_update_check=bool(data.get("auto_update_check", True)),
            discord_webhook_url=str(data.get("discord_webhook_url", "")),
            discord_auto_send=bool(data.get("discord_auto_send", False)),
            dps_alert_threshold=float(data.get("dps_alert_threshold", 0.0)),
            dps_alert_cooldown=float(data.get("dps_alert_cooldown", 10.0)),
            preprocess=preprocess,
            color_ranges=color_ranges,
        )

    # ── 저장 ──────────────────────────────────────────────

    def save(self, config: AppConfig, path: Path | None = None) -> None:
        """AppConfig를 TOML 문자열로 직렬화하여 저장한다."""
        target = path or self.default_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._serialize(config), encoding="utf-8")

    # ── 직렬화 ────────────────────────────────────────────

    @staticmethod
    def _escape_toml_str(value: str) -> str:
        """TOML 문자열 값을 이스케이프한다."""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _serialize(config: AppConfig) -> str:
        """AppConfig를 TOML 문자열로 변환한다 (외부 의존성 없음)."""
        _esc = ConfigManager._escape_toml_str
        lines: list[str] = []

        lines.append(f"fps = {config.fps}")
        lines.append(f'ocr_engine = "{_esc(config.ocr_engine)}"')
        lines.append(f'ocr_fallback = "{_esc(config.ocr_fallback)}"')
        lines.append(f'ocr_mode = "{_esc(config.ocr_mode)}"')
        lines.append(f"ocr_debug = {'true' if config.ocr_debug else 'false'}")
        lines.append(f"idle_timeout = {config.idle_timeout}")
        lines.append(f"overlay_opacity = {config.overlay_opacity}")
        lines.append(f"overlay_width = {config.overlay_width}")
        lines.append(f"overlay_height = {config.overlay_height}")
        if config.overlay_x is not None:
            lines.append(f"overlay_x = {config.overlay_x}")
        if config.overlay_y is not None:
            lines.append(f"overlay_y = {config.overlay_y}")
        bg = config.overlay_bg_color
        lines.append(f"overlay_bg_color = [{bg[0]}, {bg[1]}, {bg[2]}]")
        lines.append(f'hotkey_overlay = "{_esc(config.hotkey_overlay)}"')
        lines.append(f'hotkey_reset = "{_esc(config.hotkey_reset)}"')
        lines.append(f'hotkey_breakdown = "{_esc(config.hotkey_breakdown)}"')
        lines.append(f"auto_update_check = {'true' if config.auto_update_check else 'false'}")
        lines.append(f'discord_webhook_url = "{_esc(config.discord_webhook_url)}"')
        lines.append(f"discord_auto_send = {'true' if config.discord_auto_send else 'false'}")
        lines.append(f"dps_alert_threshold = {config.dps_alert_threshold}")
        lines.append(f"dps_alert_cooldown = {config.dps_alert_cooldown}")

        # preprocess
        lines.append("")
        lines.append("[preprocess]")
        lines.append(f"upscale_factor = {config.preprocess.upscale_factor}")
        lines.append(f"denoise = {'true' if config.preprocess.denoise else 'false'}")
        lines.append(f"sharpen = {'true' if config.preprocess.sharpen else 'false'}")
        lines.append(f"adaptive_threshold = {'true' if config.preprocess.adaptive_threshold else 'false'}")
        lines.append(f"cleanup_min_area = {config.preprocess.cleanup_min_area}")

        if config.roi is not None:
            lines.append("")
            lines.append("[roi]")
            lines.append(f"left = {config.roi.left}")
            lines.append(f"top = {config.roi.top}")
            lines.append(f"width = {config.roi.width}")
            lines.append(f"height = {config.roi.height}")

        if config.color_ranges:
            for cr in config.color_ranges:
                lines.append("")
                lines.append("[[color_ranges]]")
                lines.append(f'name = "{_esc(cr.name)}"')
                lines.append(f"lower = [{cr.lower[0]}, {cr.lower[1]}, {cr.lower[2]}]")
                lines.append(f"upper = [{cr.upper[0]}, {cr.upper[1]}, {cr.upper[2]}]")

        lines.append("")  # trailing newline
        return "\n".join(lines)
