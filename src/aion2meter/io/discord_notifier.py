"""Discord Webhook 알림."""

from __future__ import annotations

import json
import logging
import urllib.request
from urllib.error import URLError

from aion2meter.models import DpsSnapshot

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """Discord Webhook으로 세션 요약을 전송한다."""

    @staticmethod
    def build_embed(snapshot: DpsSnapshot, tag: str = "") -> dict:
        """Discord Embed JSON을 생성한다."""
        duration_str = f"{snapshot.elapsed_seconds:.1f}초"

        # 스킬 Top 3
        sorted_skills = sorted(
            snapshot.skill_breakdown.items(), key=lambda x: x[1], reverse=True
        )[:3]
        skill_text = "\n".join(
            f"{name}: {dmg:,}" for name, dmg in sorted_skills
        ) or "없음"

        fields = [
            {"name": "DPS", "value": f"{snapshot.dps:,.1f}", "inline": True},
            {"name": "총 대미지", "value": f"{snapshot.total_damage:,}", "inline": True},
            {"name": "지속시간", "value": duration_str, "inline": True},
            {"name": "Peak DPS", "value": f"{snapshot.peak_dps:,.1f}", "inline": True},
            {"name": "스킬 Top 3", "value": skill_text, "inline": False},
        ]

        embed: dict = {
            "title": "전투 요약",
            "color": 0x00FF64,
            "fields": fields,
        }

        if tag:
            embed["footer"] = {"text": f"태그: {tag}"}

        return embed

    @staticmethod
    def is_valid_webhook_url(url: str) -> bool:
        """Discord Webhook URL 형식을 검증한다."""
        if not url:
            return False
        return url.startswith("https://discord.com/api/webhooks/") or url.startswith(
            "https://discordapp.com/api/webhooks/"
        )

    @staticmethod
    def send_session_summary(
        snapshot: DpsSnapshot, tag: str, webhook_url: str
    ) -> bool:
        """세션 요약을 Discord로 전송한다."""
        if not DiscordNotifier.is_valid_webhook_url(webhook_url):
            logger.warning("잘못된 Discord Webhook URL: %s", webhook_url)
            return False

        embed = DiscordNotifier.build_embed(snapshot, tag)
        payload = json.dumps({"embeds": [embed]}).encode("utf-8")

        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 204
        except (URLError, OSError) as e:
            logger.error("Discord 전송 실패: %s", e)
            return False
