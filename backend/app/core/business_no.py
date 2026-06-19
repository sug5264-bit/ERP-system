"""한국 사업자등록번호(10자리) 체크섬 검증.

알고리즘 (국세청 공식):
1. 10자리 숫자만 추출 (하이픈 제거)
2. 가중치 [1,3,7,1,3,7,1,3,5]를 앞 9자리에 곱해 합산
3. 9번째 자리(index 8) × 5의 결과의 십의자리를 합에 추가
4. (10 - sum % 10) % 10 == 10번째 자리(check digit)

예시: 123-45-67890 → 유효하지 않음
     206-87-06151 → 유효 (실제 사업자번호 검증 가능)
"""
from __future__ import annotations

_WEIGHTS = (1, 3, 7, 1, 3, 7, 1, 3, 5)


def normalize_business_no(value: str | None) -> str:
    """하이픈/공백 제거 후 숫자만 반환. 비어있거나 None이면 빈 문자열."""
    if not value:
        return ""
    return "".join(c for c in value if c.isdigit())


def format_business_no(value: str | None) -> str:
    """'XXX-XX-XXXXX' 형식으로 정형화. 10자리 미만이면 그대로 반환."""
    digits = normalize_business_no(value)
    if len(digits) != 10:
        return value or ""
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


def is_valid_business_no(value: str | None) -> bool:
    """체크섬 + 형식 검증.

    None / 빈 문자열은 False. 검증 실패도 False.
    체크섬 알고리즘이 통과해도 첫 3자리(국세청 청서코드)가 000이면 거부 —
    명백한 가짜를 막기 위함.
    """
    digits = normalize_business_no(value)
    if len(digits) != 10 or not digits.isdigit():
        return False
    # 첫 3자리가 000이면 무효 (국세청 코드는 절대 000이 아님)
    if digits[:3] == "000":
        return False
    try:
        total = sum(int(digits[i]) * _WEIGHTS[i] for i in range(9))
        # 9번째(index 8) × 5의 결과의 십의자리만 추가로 가산
        total += (int(digits[8]) * 5) // 10
        check = (10 - total % 10) % 10
        return check == int(digits[9])
    except (ValueError, IndexError):
        return False
