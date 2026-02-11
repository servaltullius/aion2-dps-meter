"""Discord 알림 단위 테스트."""

from __future__ import annotations

import json

import pytest

from aion2meter.io.discord_notifier import DiscordNotifier
from aion2meter.models import DpsSnapshot


def _sample_snapshot() -> DpsSnapshot:
    return DpsSnapshot(
        dps=2750.0,
        total_damage=5500,
        elapsed_seconds=2.0,
        peak_dps=3100.0,
        combat_active=False,
        skill_breakdown={"검격": 2300, "마법": 3200},
        event_count=3,
    )


class TestBuildEmbed:
    """Embed JSON 생성 검증."""

    def test_embed_has_required_fields(self) -> None:
        """Embed에 title, fields, color가 있다."""
        embed = DiscordNotifier.build_embed(_sample_snapshot(), tag="보스1")
        assert "title" in embed
        assert "fields" in embed
        assert "color" in embed

    def test_embed_fields_include_dps(self) -> None:
        """fields에 DPS 정보가 포함된다."""
        embed = DiscordNotifier.build_embed(_sample_snapshot(), tag="")
        field_names = [f["name"] for f in embed["fields"]]
        assert "DPS" in field_names
        assert "총 대미지" in field_names
        assert "Peak DPS" in field_names

    def test_embed_includes_tag_when_provided(self) -> None:
        """태그가 있으면 footer에 표시된다."""
        embed = DiscordNotifier.build_embed(_sample_snapshot(), tag="보스A")
        assert "footer" in embed
        assert "보스A" in embed["footer"]["text"]

    def test_embed_no_footer_without_tag(self) -> None:
        """태그가 없으면 footer가 없다."""
        embed = DiscordNotifier.build_embed(_sample_snapshot(), tag="")
        assert "footer" not in embed

    def test_embed_top3_skills(self) -> None:
        """스킬 Top 3가 표시된다."""
        embed = DiscordNotifier.build_embed(_sample_snapshot(), tag="")
        field_names = [f["name"] for f in embed["fields"]]
        assert "스킬 Top 3" in field_names


class TestWebhookValidation:
    """Webhook URL 검증."""

    def test_valid_discord_url(self) -> None:
        url = "https://discord.com/api/webhooks/123/abc"
        assert DiscordNotifier.is_valid_webhook_url(url) is True

    def test_invalid_url(self) -> None:
        assert DiscordNotifier.is_valid_webhook_url("") is False
        assert DiscordNotifier.is_valid_webhook_url("http://example.com") is False

    def test_discordapp_url_also_valid(self) -> None:
        url = "https://discordapp.com/api/webhooks/123/abc"
        assert DiscordNotifier.is_valid_webhook_url(url) is True
