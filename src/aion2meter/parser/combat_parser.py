"""한국어 전투 로그 파서."""

from __future__ import annotations

import re

from aion2meter.models import DamageEvent, HitType

# HitType 매핑
_HIT_TYPE_MAP: dict[str, HitType] = {
    "치명타": HitType.CRITICAL,
    "완벽": HitType.PERFECT,
    "강타": HitType.STRONG,
    "강타 치명타": HitType.STRONG_CRITICAL,
    "강타치명타": HitType.STRONG_CRITICAL,
    "완벽 치명타": HitType.PERFECT_CRITICAL,
    "완벽치명타": HitType.PERFECT_CRITICAL,
}

# OCR 텍스트 보정 (키워드 수준)
_OCR_TEXT_CORRECTIONS: dict[str, str] = {
    "대머지": "대미지",
    "대미저": "대미지",
    "대머저": "대미지",
}

# OCR 숫자 보정 (숫자 컨텍스트에서 적용)
_OCR_DIGIT_MAP: dict[str, str] = {
    "O": "0",
    "o": "0",
    "l": "1",
    "I": "1",
    "B": "8",
    "S": "5",
    "Z": "2",
    "G": "6",
}

# OCR로 인해 숫자 위치에 나올 수 있는 문자 패턴
# \d 외에도 O, o, l, I, B, S, Z, G 등이 OCR 오류로 나올 수 있음
_NUM = r"[\d,.\-OolIBSZG]"
_NUM_START = r"[\dOolIBSZG]"

# 정규식: 배율(치명타/완벽/강타 등) 포함 대미지
# 긴 패턴(강타 치명타, 완벽 치명타)을 먼저 시도하도록 순서 지정
_RE_MODIFIER = re.compile(
    rf"(.*?)에게\s*(강타\s*치명타|완벽\s*치명타|치명타|완벽|강타)\s+(.*?)[을를]\s*사용해\s*.*?({_NUM_START}{_NUM}*)\s*의\s*대미지를\s*줬습니다"
)

# 정규식: 일반 대미지 (배율 없음)
_RE_NORMAL = re.compile(
    rf"(.*?)에게\s+(.*?)[을를]\s*사용해\s*.*?({_NUM_START}{_NUM}*)\s*의\s*대미지를\s*줬습니다"
)

# 정규식: 추가 대미지
_RE_ADDITIONAL = re.compile(
    rf"(.*?)에게\s*추가로\s*({_NUM_START}{_NUM}*)\s*의\s*대미지를\s*줬습니다"
)


def _fix_ocr_text(text: str) -> str:
    """OCR 텍스트 보정 (키워드 수준)."""
    for wrong, correct in _OCR_TEXT_CORRECTIONS.items():
        text = text.replace(wrong, correct)
    return text


def _fix_ocr_digits(num_str: str) -> str:
    """숫자 문자열에서 OCR 오류 보정."""
    result: list[str] = []
    for ch in num_str:
        if ch in _OCR_DIGIT_MAP:
            result.append(_OCR_DIGIT_MAP[ch])
        else:
            result.append(ch)
    return "".join(result)


def _parse_number(raw: str) -> int:
    """콤마, 소수점 포함 숫자 문자열을 int로 변환."""
    # OCR 오류 보정
    fixed = _fix_ocr_digits(raw)
    # 콤마 제거
    fixed = fixed.replace(",", "")
    # 소수점 이하 버림
    if "." in fixed:
        fixed = fixed.split(".")[0]
    return int(fixed)


class KoreanCombatParser:
    """한국어 아이온2 전투 로그 파서.

    CombatLogParser Protocol 구현체.
    """

    def parse(self, text: str, timestamp: float) -> list[DamageEvent]:
        """텍스트를 줄 단위로 분리하여 대미지 이벤트를 파싱한다."""
        events: list[DamageEvent] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # OCR 텍스트 보정 적용
            line = _fix_ocr_text(line)
            # 각 패턴 시도
            event = self._parse_line(line, timestamp)
            if event is not None:
                events.append(event)
        return events

    def _parse_line(self, line: str, timestamp: float) -> DamageEvent | None:
        """한 줄을 파싱하여 DamageEvent를 반환. 매칭 실패 시 None."""
        # 1) 추가 대미지 먼저 체크 (더 구체적)
        m = _RE_ADDITIONAL.search(line)
        if m:
            target = m.group(1).strip()
            damage = _parse_number(m.group(2))
            return DamageEvent(
                timestamp=timestamp,
                source="",
                target=target,
                skill="",
                damage=damage,
                hit_type=HitType.NORMAL,
                is_additional=True,
            )

        # 2) 배율 포함 대미지 (치명타, 완벽, 강타 등)
        m = _RE_MODIFIER.search(line)
        if m:
            target = m.group(1).strip()
            modifier_raw = m.group(2).strip()
            # 공백 정규화: "강타 치명타" vs "강타  치명타"
            modifier_key = re.sub(r"\s+", " ", modifier_raw)
            skill = m.group(3).strip()
            damage = _parse_number(m.group(4))
            hit_type = _HIT_TYPE_MAP.get(modifier_key, HitType.NORMAL)
            return DamageEvent(
                timestamp=timestamp,
                source="",
                target=target,
                skill=skill,
                damage=damage,
                hit_type=hit_type,
                is_additional=False,
            )

        # 3) 일반 대미지 (배율 없음)
        m = _RE_NORMAL.search(line)
        if m:
            target = m.group(1).strip()
            skill = m.group(2).strip()
            damage = _parse_number(m.group(3))
            return DamageEvent(
                timestamp=timestamp,
                source="",
                target=target,
                skill=skill,
                damage=damage,
                hit_type=HitType.NORMAL,
                is_additional=False,
            )

        return None
