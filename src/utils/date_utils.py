import re
from datetime import datetime, timedelta


def parse_korean_date(date_str: str) -> datetime:
    """
    한국어 날짜 형식 '2026. 4. 5.' 을 datetime으로 파싱합니다.
    '까지', 공백 등 불필요한 문자는 자동 제거합니다.
    """
    # 숫자만 추출
    numbers = re.findall(r"\d+", date_str)
    if len(numbers) < 3:
        raise ValueError(f"날짜 파싱 실패: '{date_str}'")
    year, month, day = int(numbers[0]), int(numbers[1]), int(numbers[2])
    return datetime(year, month, day)


def format_korean_date(dt: datetime) -> str:
    """
    datetime을 한국어 날짜 형식 '2026. 4. 12.' 으로 변환합니다.
    Element UI datepicker 입력에 사용됩니다.
    """
    return f"{dt.year}. {dt.month}. {dt.day}."


def is_date_before(date_str: str, reference_str: str) -> bool:
    """
    date_str이 reference_str보다 이전 날짜이면 True를 반환합니다.

    예: '2026. 4. 4.' < '2026. 4. 12.' → True
    """
    return parse_korean_date(date_str) < parse_korean_date(reference_str)


def add_one_week(date_str: str) -> str:
    """
    한국어 날짜 문자열에 7일을 더한 날짜를 반환합니다.

    예: '2026. 4. 5.' → '2026. 4. 12.'
    """
    dt = parse_korean_date(date_str)
    new_dt = dt + timedelta(weeks=1)
    return format_korean_date(new_dt)
