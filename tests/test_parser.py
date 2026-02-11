"""전투 로그 파서 단위 테스트 (TDD - RED 먼저)."""

import pytest

from aion2meter.models import DamageEvent, HitType
from aion2meter.parser.combat_parser import KoreanCombatParser
from aion2meter.protocols import CombatLogParser


@pytest.fixture
def parser() -> KoreanCombatParser:
    return KoreanCombatParser()


class TestProtocolCompliance:
    """KoreanCombatParser가 CombatLogParser Protocol을 구현하는지 확인."""

    def test_implements_protocol(self, parser: KoreanCombatParser):
        assert isinstance(parser, CombatLogParser)

    def test_parse_returns_list_of_damage_events(self, parser: KoreanCombatParser):
        result = parser.parse("아무 텍스트", 1.0)
        assert isinstance(result, list)


class TestNormalDamage:
    """일반 대미지 파싱."""

    def test_normal_damage(self, parser: KoreanCombatParser):
        text = "몬스터에게 검격을 사용해 1,234의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        evt = events[0]
        assert evt.target == "몬스터"
        assert evt.skill == "검격"
        assert evt.damage == 1234
        assert evt.hit_type == HitType.NORMAL
        assert evt.is_additional is False
        assert evt.timestamp == 1.0

    def test_normal_damage_without_comma(self, parser: KoreanCombatParser):
        text = "몬스터에게 검격을 사용해 500의 대미지를 줬습니다."
        events = parser.parse(text, 2.0)
        assert len(events) == 1
        assert events[0].damage == 500


class TestCriticalDamage:
    """치명타 대미지 파싱."""

    def test_critical_damage(self, parser: KoreanCombatParser):
        text = "몬스터에게 치명타 검격을 사용해 2,468의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        evt = events[0]
        assert evt.target == "몬스터"
        assert evt.skill == "검격"
        assert evt.damage == 2468
        assert evt.hit_type == HitType.CRITICAL


class TestPerfectDamage:
    """완벽 대미지 파싱."""

    def test_perfect_damage(self, parser: KoreanCombatParser):
        text = "몬스터에게 완벽 검격을 사용해 1,851의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        evt = events[0]
        assert evt.skill == "검격"
        assert evt.damage == 1851
        assert evt.hit_type == HitType.PERFECT


class TestStrongDamage:
    """강타 대미지 파싱."""

    def test_strong_damage(self, parser: KoreanCombatParser):
        text = "몬스터에게 강타 검격을 사용해 1,851의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        evt = events[0]
        assert evt.skill == "검격"
        assert evt.damage == 1851
        assert evt.hit_type == HitType.STRONG


class TestStrongCriticalDamage:
    """강타 치명타 대미지 파싱."""

    def test_strong_critical_damage(self, parser: KoreanCombatParser):
        text = "몬스터에게 강타 치명타 검격을 사용해 3,702의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        evt = events[0]
        assert evt.skill == "검격"
        assert evt.damage == 3702
        assert evt.hit_type == HitType.STRONG_CRITICAL


class TestPerfectCriticalDamage:
    """완벽 치명타 대미지 파싱."""

    def test_perfect_critical_damage(self, parser: KoreanCombatParser):
        text = "몬스터에게 완벽 치명타 검격을 사용해 3,702의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        evt = events[0]
        assert evt.skill == "검격"
        assert evt.damage == 3702
        assert evt.hit_type == HitType.PERFECT_CRITICAL


class TestAdditionalDamage:
    """추가 대미지 파싱."""

    def test_additional_damage(self, parser: KoreanCombatParser):
        text = "몬스터에게 추가로 500의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        evt = events[0]
        assert evt.target == "몬스터"
        assert evt.skill == ""
        assert evt.damage == 500
        assert evt.hit_type == HitType.NORMAL
        assert evt.is_additional is True


class TestMultiline:
    """멀티라인 로그 파싱."""

    def test_multiline_parsing(self, parser: KoreanCombatParser):
        text = (
            "몬스터에게 검격을 사용해 1,234의 대미지를 줬습니다.\n"
            "몬스터에게 치명타 검격을 사용해 2,468의 대미지를 줬습니다.\n"
            "몬스터에게 추가로 500의 대미지를 줬습니다."
        )
        events = parser.parse(text, 1.0)
        assert len(events) == 3
        assert events[0].damage == 1234
        assert events[0].hit_type == HitType.NORMAL
        assert events[1].damage == 2468
        assert events[1].hit_type == HitType.CRITICAL
        assert events[2].damage == 500
        assert events[2].is_additional is True

    def test_multiline_with_empty_lines(self, parser: KoreanCombatParser):
        text = (
            "몬스터에게 검격을 사용해 100의 대미지를 줬습니다.\n"
            "\n"
            "몬스터에게 검격을 사용해 200의 대미지를 줬습니다."
        )
        events = parser.parse(text, 1.0)
        assert len(events) == 2


class TestOcrCorrection:
    """OCR 오류 보정 테스트."""

    def test_대머지_correction(self, parser: KoreanCombatParser):
        text = "몬스터에게 검격을 사용해 1,234의 대머지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        assert events[0].damage == 1234

    def test_number_O_to_0(self, parser: KoreanCombatParser):
        text = "몬스터에게 검격을 사용해 1,O34의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        assert events[0].damage == 1034

    def test_number_l_to_1(self, parser: KoreanCombatParser):
        text = "몬스터에게 검격을 사용해 l,234의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        assert events[0].damage == 1234

    def test_number_B_to_8(self, parser: KoreanCombatParser):
        text = "몬스터에게 검격을 사용해 1,B34의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        assert events[0].damage == 1834


class TestNoMatch:
    """매칭 안 되는 텍스트 처리."""

    def test_no_match_returns_empty(self, parser: KoreanCombatParser):
        text = "전혀 관련 없는 텍스트입니다."
        events = parser.parse(text, 1.0)
        assert events == []

    def test_empty_string_returns_empty(self, parser: KoreanCombatParser):
        events = parser.parse("", 1.0)
        assert events == []

    def test_whitespace_only_returns_empty(self, parser: KoreanCombatParser):
        events = parser.parse("   \n  \n  ", 1.0)
        assert events == []


class TestDecimalDamage:
    """소수점 포함 숫자 파싱."""

    def test_decimal_damage_truncated_to_int(self, parser: KoreanCombatParser):
        text = "몬스터에게 검격을 사용해 1,234.5의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        assert events[0].damage == 1234


class TestSourceExtraction:
    """시전자(source) 추출 테스트."""

    def test_default_source(self, parser: KoreanCombatParser):
        """소스가 명시되지 않은 로그 → 기본 source는 빈 문자열 또는 'player'."""
        text = "몬스터에게 검격을 사용해 1,000의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        # 아이온2 로그 형식상 시전자가 명시되지 않으면 플레이어 본인
        assert events[0].source == ""

    def test_additional_damage_source(self, parser: KoreanCombatParser):
        text = "몬스터에게 추가로 500의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert events[0].source == ""


class TestVariousTargets:
    """다양한 대상 이름 파싱."""

    def test_long_target_name(self, parser: KoreanCombatParser):
        text = "어둠의 마법사에게 검격을 사용해 999의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        assert events[0].target == "어둠의 마법사"

    def test_target_with_를(self, parser: KoreanCombatParser):
        text = "드래곤에게 화염구를 사용해 5,000의 대미지를 줬습니다."
        events = parser.parse(text, 1.0)
        assert len(events) == 1
        assert events[0].target == "드래곤"
        assert events[0].skill == "화염구"
