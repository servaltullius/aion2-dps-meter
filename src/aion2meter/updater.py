"""GitHub Releases 기반 자동 업데이트 확인."""

from __future__ import annotations

import json
import logging
import urllib.request

logger = logging.getLogger(__name__)

_RELEASES_URL = (
    "https://api.github.com/repos/servaltullius/aion2-dps-meter/releases/latest"
)


def compare_versions(current: str, latest: str) -> bool:
    """latest가 current보다 새 버전이면 True를 반환한다."""
    def _normalize(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.lstrip("v").split("."))

    return _normalize(latest) > _normalize(current)


def parse_release_info(raw_json: str) -> tuple[str, str]:
    """GitHub API JSON에서 (version, download_url)을 추출한다.

    Raises:
        ValueError: JSON 파싱 실패
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}") from e

    tag = data["tag_name"]
    version = tag.lstrip("v")

    assets = data.get("assets", [])
    download_url = data.get("html_url", "")
    for asset in assets:
        if asset["name"].endswith(".exe"):
            download_url = asset["browser_download_url"]
            break

    return version, download_url


def check_for_update(current_version: str) -> tuple[str, str] | None:
    """GitHub에서 최신 릴리스를 확인한다.

    Returns:
        (latest_version, download_url) 또는 None (업데이트 없거나 실패)
    """
    try:
        req = urllib.request.Request(
            _RELEASES_URL,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")

        version, url = parse_release_info(raw)
        if compare_versions(current_version, version):
            return version, url
        return None
    except Exception:
        logger.debug("업데이트 확인 실패", exc_info=True)
        return None
