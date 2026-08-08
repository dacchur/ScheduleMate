import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


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

def is_date_after(date_str: str, reference_str: str) -> bool:
    return parse_korean_date(date_str) > parse_korean_date(reference_str)

def add_one_week(date_str: str) -> str:
    """
    한국어 날짜 문자열에 7일을 더한 날짜를 반환합니다.

    예: '2026. 4. 5.' → '2026. 4. 12.'
    """
    dt = parse_korean_date(date_str)
    new_dt = dt + timedelta(weeks=1)
    return format_korean_date(new_dt)

def subtract_one_week(data_str: str) -> str:
    """
    한국어 날짜 문자열에 7일을 뺀 날짜를 반환합니다.

    예: '2026. 4. 12.' -> '2026. 4. 5.'
    """
    dt = parse_korean_date(data_str)
    new_dt = dt - timedelta(weeks=1)
    return format_korean_date(new_dt)

def get_kst_today() -> date:
    """컨테이너의 시스템 시간대와 관계없이 한국 기준 오늘 날짜를 반환합니다."""
    return datetime.now(KST).date()


def get_date_one_week_from_now(base_date: date | None = None) -> str:
    """한국 기준 실행일(또는 전달한 기준일)의 7일 뒤 날짜를 반환합니다."""
    if base_date is None:
        base_date = get_kst_today()
    target_date = base_date + timedelta(weeks=1)
    return format_korean_date(
        datetime(target_date.year, target_date.month, target_date.day)
    )
