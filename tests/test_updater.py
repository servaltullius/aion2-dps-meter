"""자동 업데이트 확인 단위 테스트."""

from __future__ import annotations

import json

import pytest

from aion2meter.updater import compare_versions, parse_release_info


class TestVersionCompare:
    """버전 비교 로직."""

    def test_newer_version(self):
        assert compare_versions("0.1.0", "0.2.0") is True

    def test_same_version(self):
        assert compare_versions("0.1.0", "0.1.0") is False

    def test_older_version(self):
        assert compare_versions("0.2.0", "0.1.0") is False

    def test_patch_version(self):
        assert compare_versions("0.1.0", "0.1.1") is True

    def test_major_version(self):
        assert compare_versions("0.9.9", "1.0.0") is True

    def test_with_v_prefix(self):
        assert compare_versions("0.1.0", "v0.2.0") is True

    def test_both_v_prefix(self):
        assert compare_versions("v0.1.0", "v0.1.0") is False


class TestParseReleaseInfo:
    """GitHub API 응답 파싱."""

    def test_parse_valid_response(self):
        data = json.dumps({
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/servaltullius/aion2-dps-meter/releases/tag/v0.2.0",
            "assets": [
                {
                    "name": "aion2meter.exe",
                    "browser_download_url": "https://example.com/aion2meter.exe",
                }
            ],
        })
        version, url = parse_release_info(data)
        assert version == "0.2.0"
        assert "aion2meter" in url

    def test_parse_no_assets(self):
        data = json.dumps({
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/servaltullius/aion2-dps-meter/releases/tag/v0.2.0",
            "assets": [],
        })
        version, url = parse_release_info(data)
        assert version == "0.2.0"
        assert "releases" in url

    def test_parse_invalid_json(self):
        with pytest.raises(ValueError):
            parse_release_info("not json")
