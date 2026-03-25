"""한국어 TTS를 위한 숫자 전처리

콤마 구분 숫자(14,000명)를 한국어 단위(1만4천명)로 변환하고,
퍼센트(33.5%)를 한글 발음(33점5퍼센트)으로 변환하여
TTS가 올바르게 발음하도록 함.
"""

import re

# 한글 접미사 패턴 (숫자 뒤에 붙는 단위)
_SUFFIX = r"명|건|곳|개|장|원|대|채|배|억|만|개월|년|달러|위|위안|조|번|회|권|편|척|기"


def _num_to_korean(num: int) -> str:
    """정수를 한국어 만/천/백 단위 표현으로 변환 (공백 없이)

    54836 → '5만4천8백36'
    14000 → '1만4천'
    1600  → '1천6백'
    """
    if num == 0:
        return "0"

    parts = []

    if num >= 100_000_000:
        eok = num // 100_000_000
        num %= 100_000_000
        parts.append(f"{eok}억")

    if num >= 10_000:
        man = num // 10_000
        num %= 10_000
        parts.append(f"{man}만")

    if num >= 1_000:
        cheon = num // 1_000
        num %= 1_000
        parts.append(f"{cheon}천")

    if num >= 100:
        baek = num // 100
        num %= 100
        parts.append(f"{baek}백")

    if num > 0:
        parts.append(str(num))

    return "".join(parts)


def convert_numbers_for_tts(text: str) -> str:
    """TTS 전송 전 숫자를 한국어 발음 친화적으로 변환

    1) 콤마 구분 숫자 + 접미사: 14,000명 → 1만4천명
    2) 콤마 없는 큰 숫자 + 접미사: 54836건 → 5만4천8백36건
    3) 소수점 퍼센트: 33.5% → 33점5퍼센트
    4) 정수 퍼센트: 55% → 55퍼센트
    """

    def _replace_comma_num(match):
        num_str = match.group(1).replace(",", "")
        suffix = match.group(2)
        num = int(num_str)
        if num < 1000:
            return match.group(0)
        return f"{_num_to_korean(num)}{suffix}"

    def _replace_plain_num(match):
        num_str = match.group(1)
        suffix = match.group(2)
        num = int(num_str)
        # 연도(1900~2099년)는 TTS가 올바르게 읽으므로 변환하지 않음
        if suffix == "년" and 1900 <= num <= 2099:
            return match.group(0)
        if num < 1000:
            return match.group(0)
        return f"{_num_to_korean(num)}{suffix}"

    # 1) 콤마 구분 숫자 + 한글 접미사
    text = re.sub(
        rf"(\d{{1,3}}(?:,\d{{3}})+)({_SUFFIX})",
        _replace_comma_num,
        text,
    )

    # 2) 콤마 없는 4자리 이상 숫자 + 한글 접미사 (연도 제외)
    text = re.sub(
        rf"(\d{{4,}})({_SUFFIX})",
        _replace_plain_num,
        text,
    )

    # 3) 소수점 퍼센트: 35.6% → 35점6퍼센트
    text = re.sub(
        r"(\d+)\.(\d+)%",
        r"\1점\2퍼센트",
        text,
    )

    # 4) 정수 퍼센트: 55% → 55퍼센트
    text = re.sub(
        r"(\d+)%",
        r"\1퍼센트",
        text,
    )

    return text
