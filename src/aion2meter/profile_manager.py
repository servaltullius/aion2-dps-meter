"""직업별 프로파일 관리 (TOML)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from aion2meter.models import AppConfig, ROI

_DEFAULT_PATH = Path.home() / ".aion2meter" / "profiles.toml"


class ProfileManager:
    """직업별 ROI/OCR 설정을 TOML 파일로 저장/전환한다."""

    def __init__(self, profiles_path: Path | None = None) -> None:
        self._path = profiles_path or _DEFAULT_PATH
        self._data: dict = self._load_file()

    def _load_file(self) -> dict:
        if not self._path.exists():
            return {"active": "", "profiles": {}}
        with open(self._path, "rb") as f:
            data = tomllib.load(f)
        data.setdefault("active", "")
        data.setdefault("profiles", {})
        return data

    def _save_file(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        lines.append(f'active = "{self._data["active"]}"')

        for name, prof in self._data["profiles"].items():
            lines.append("")
            lines.append(f'[profiles."{name}"]')
            if prof.get("roi_left") is not None:
                lines.append(f"roi_left = {prof['roi_left']}")
                lines.append(f"roi_top = {prof['roi_top']}")
                lines.append(f"roi_width = {prof['roi_width']}")
                lines.append(f"roi_height = {prof['roi_height']}")
            lines.append(f'ocr_engine = "{prof.get("ocr_engine", "winocr")}"')
            lines.append(f"idle_timeout = {prof.get('idle_timeout', 5.0)}")

        lines.append("")
        self._path.write_text("\n".join(lines), encoding="utf-8")

    def list_profiles(self) -> list[str]:
        return list(self._data["profiles"].keys())

    def get_active(self) -> str:
        return self._data["active"]

    def switch_profile(self, name: str) -> AppConfig:
        if name not in self._data["profiles"]:
            raise KeyError(f"프로파일 '{name}'이 존재하지 않습니다.")
        self._data["active"] = name
        self._save_file()
        return self._profile_to_config(self._data["profiles"][name])

    def save_current_as(self, name: str, config: AppConfig) -> None:
        prof: dict = {
            "ocr_engine": config.ocr_engine,
            "idle_timeout": config.idle_timeout,
        }
        if config.roi is not None:
            prof["roi_left"] = config.roi.left
            prof["roi_top"] = config.roi.top
            prof["roi_width"] = config.roi.width
            prof["roi_height"] = config.roi.height
        self._data["profiles"][name] = prof
        self._data["active"] = name
        self._save_file()

    def delete_profile(self, name: str) -> None:
        self._data["profiles"].pop(name, None)
        if self._data["active"] == name:
            self._data["active"] = ""
        self._save_file()

    @staticmethod
    def _profile_to_config(prof: dict) -> AppConfig:
        roi = None
        if prof.get("roi_left") is not None:
            roi = ROI(
                left=int(prof["roi_left"]),
                top=int(prof["roi_top"]),
                width=int(prof["roi_width"]),
                height=int(prof["roi_height"]),
            )
        return AppConfig(
            roi=roi,
            ocr_engine=str(prof.get("ocr_engine", "winocr")),
            idle_timeout=float(prof.get("idle_timeout", 5.0)),
        )
