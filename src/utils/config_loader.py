import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

_ROOT = Path(__file__).parent.parent.parent
_CONFIG_PATH = _ROOT / "config" / "config.json"

# 요일 이름 → APScheduler cron 값 매핑 (한국어/영어 모두 지원)
_DAY_OF_WEEK_MAP = {
    # 영어 전체
    "monday": "mon", "tuesday": "tue", "wednesday": "wed",
    "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun",
    # 영어 약어
    "mon": "mon", "tue": "tue", "wed": "wed",
    "thu": "thu", "fri": "fri", "sat": "sat", "sun": "sun",
    # 한국어
    "월요일": "mon", "화요일": "tue", "수요일": "wed",
    "목요일": "thu", "금요일": "fri", "토요일": "sat", "일요일": "sun",
    "월": "mon", "화": "tue", "수": "wed",
    "목": "thu", "금": "fri", "토": "sat", "일": "sun",
}


@dataclass
class ScheduleConfig:
    frequency: str       # "daily" | "weekly" | "monthly"
    hour: int
    minute: int
    day_of_week: str     # APScheduler 형식 (mon~sun), weekly일 때 사용
    day_of_month: int    # 1~28, monthly일 때 사용

    def describe(self) -> str:
        """사람이 읽기 쉬운 스케줄 설명 반환"""
        time_str = f"{self.hour:02d}:{self.minute:02d} KST"
        if self.frequency == "daily":
            return f"매일 {time_str}"
        elif self.frequency == "weekly":
            kor_day = {v: k for k, v in _DAY_OF_WEEK_MAP.items() if len(k) == 3 and k.isalpha()}.get(
                self.day_of_week, self.day_of_week
            )
            return f"매주 {self.day_of_week}요일 {time_str}"
        elif self.frequency == "monthly":
            return f"매월 {self.day_of_month}일 {time_str}"
        return f"{self.frequency} {time_str}"


@dataclass
class AppConfig:
    schedule: ScheduleConfig
    keywords: List[str]
    login_id: str
    login_password: str
    headless: bool


def load_config(config_path: Path | None = None) -> AppConfig:
    """
    config/config.json 을 읽어 AppConfig 를 반환합니다.
    실행 시점마다 새로 읽으므로 재시작 없이 설정 변경이 반영됩니다.
    """
    if config_path is None:
        config_path = _CONFIG_PATH

    if not config_path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")

    raw = json.loads(config_path.read_text(encoding="utf-8"))

    # ── 스케줄 파싱 ────────────────────────────────────────────────────────
    sched_raw = raw.get("schedule", {})

    frequency = sched_raw.get("frequency", "weekly").lower()
    if frequency not in ("daily", "weekly", "monthly"):
        raise ValueError(f"schedule.frequency 값이 올바르지 않습니다: '{frequency}' (daily / weekly / monthly 중 하나)")

    time_str = sched_raw.get("time", "20:00")
    try:
        hour, minute = map(int, time_str.split(":"))
    except ValueError:
        raise ValueError(f"schedule.time 형식이 올바르지 않습니다: '{time_str}' (HH:MM 형식 사용)")

    # 요일 파싱 (weekly 전용)
    raw_dow = str(sched_raw.get("day_of_week", "saturday")).lower()
    day_of_week = _DAY_OF_WEEK_MAP.get(raw_dow)
    if day_of_week is None:
        raise ValueError(f"schedule.day_of_week 값이 올바르지 않습니다: '{raw_dow}'")

    # 월 날짜 파싱 (monthly 전용)
    day_of_month = int(sched_raw.get("day_of_month", 1))
    if not (1 <= day_of_month <= 28):
        raise ValueError(f"schedule.day_of_month 는 1~28 사이여야 합니다: {day_of_month}")

    schedule = ScheduleConfig(
        frequency=frequency,
        hour=hour,
        minute=minute,
        day_of_week=day_of_week,
        day_of_month=day_of_month,
    )

    # ── 키워드 파싱 ────────────────────────────────────────────────────────
    keywords = [kw.strip() for kw in raw.get("keywords", []) if kw.strip()]
    if not keywords:
        raise ValueError("config.json의 keywords 목록이 비어 있습니다.")

    # ── 로그인 정보 파싱 ───────────────────────────────────────────────────
    login_raw = raw.get("login", {})
    login_id = str(login_raw.get("id", "")).strip()
    login_password = str(login_raw.get("password", "")).strip()
    if not login_id or not login_password:
        raise ValueError("config.json의 login.id와 login.password를 설정해주세요.")

    # ── headless 파싱 ──────────────────────────────────────────────────────
    headless = bool(raw.get("headless", True))

    return AppConfig(
        schedule=schedule,
        keywords=keywords,
        login_id=login_id,
        login_password=login_password,
        headless=headless,
    )
