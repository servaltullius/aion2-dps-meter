"""프로파일 관리 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from aion2meter.models import AppConfig, ROI
from aion2meter.profile_manager import ProfileManager


@pytest.fixture()
def pm(tmp_path: Path) -> ProfileManager:
    return ProfileManager(profiles_path=tmp_path / "profiles.toml")


class TestProfileManager:
    """프로파일 CRUD 검증."""

    def test_list_empty(self, pm: ProfileManager) -> None:
        """초기 프로파일 목록은 비어있다."""
        assert pm.list_profiles() == []

    def test_save_and_list(self, pm: ProfileManager) -> None:
        """프로파일 저장 후 목록에 나타난다."""
        config = AppConfig(
            roi=ROI(left=100, top=200, width=400, height=80),
            ocr_engine="winocr",
            idle_timeout=5.0,
        )
        pm.save_current_as("마법사", config)
        assert "마법사" in pm.list_profiles()

    def test_get_active_default(self, pm: ProfileManager) -> None:
        """프로파일이 없으면 active는 빈 문자열이다."""
        assert pm.get_active() == ""

    def test_switch_profile(self, pm: ProfileManager) -> None:
        """프로파일 전환 시 해당 설정을 반환한다."""
        config = AppConfig(
            roi=ROI(left=100, top=200, width=400, height=80),
            ocr_engine="winocr",
            idle_timeout=5.0,
        )
        pm.save_current_as("마법사", config)
        loaded = pm.switch_profile("마법사")
        assert loaded.roi is not None
        assert loaded.roi.left == 100
        assert loaded.ocr_engine == "winocr"
        assert pm.get_active() == "마법사"

    def test_delete_profile(self, pm: ProfileManager) -> None:
        """프로파일을 삭제하면 목록에서 사라진다."""
        config = AppConfig(ocr_engine="tesseract")
        pm.save_current_as("궁수", config)
        pm.delete_profile("궁수")
        assert "궁수" not in pm.list_profiles()

    def test_switch_nonexistent_raises(self, pm: ProfileManager) -> None:
        """존재하지 않는 프로파일 전환 시 KeyError."""
        with pytest.raises(KeyError):
            pm.switch_profile("없는프로파일")

    def test_multiple_profiles(self, pm: ProfileManager) -> None:
        """여러 프로파일을 저장하고 전환한다."""
        cfg1 = AppConfig(roi=ROI(left=10, top=20, width=100, height=50), ocr_engine="winocr")
        cfg2 = AppConfig(roi=ROI(left=50, top=60, width=200, height=100), ocr_engine="tesseract")
        pm.save_current_as("마법사", cfg1)
        pm.save_current_as("궁수", cfg2)

        loaded = pm.switch_profile("궁수")
        assert loaded.roi is not None
        assert loaded.roi.left == 50
        assert loaded.ocr_engine == "tesseract"
