"""
스튜디오메이트 그룹수업 종료일 자동 연장 스크립트

실행 방법:
    # 즉시 1회 실행
    python src/main.py --run-now

    # 스케줄러 모드 (config/config.json 설정에 따라 자동 실행)
    python src/main.py
"""

import asyncio
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from src.automator import run_automation
from src.utils.config_loader import load_config, ScheduleConfig

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="INFO",
)
logger.add(
    LOG_DIR / "auto_launch_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    level="DEBUG",
    rotation="1 day",
    retention="30 days",
    encoding="utf-8",
)

KST = pytz.timezone("Asia/Seoul")


def parse_test_date(value: str):
    """CLI의 YYYY-MM-DD 테스트 날짜를 date로 변환합니다."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"테스트 날짜는 YYYY-MM-DD 형식이어야 합니다: '{value}'"
        ) from e


def build_cron_trigger(schedule: ScheduleConfig) -> CronTrigger:
    """
    ScheduleConfig 를 APScheduler CronTrigger 로 변환합니다.

    frequency:
        daily   → 매일 HH:MM
        weekly  → 매주 day_of_week 요일 HH:MM
        monthly → 매월 day_of_month 일 HH:MM
    """
    if schedule.frequency == "daily":
        return CronTrigger(
            hour=schedule.hour,
            minute=schedule.minute,
            timezone=KST,
        )
    elif schedule.frequency == "weekly":
        return CronTrigger(
            day_of_week=schedule.day_of_week,
            hour=schedule.hour,
            minute=schedule.minute,
            timezone=KST,
        )
    elif schedule.frequency == "monthly":
        return CronTrigger(
            day=schedule.day_of_month,
            hour=schedule.hour,
            minute=schedule.minute,
            timezone=KST,
        )
    else:
        raise ValueError(f"지원하지 않는 frequency: {schedule.frequency}")


async def scheduled_job() -> None:
    """스케줄러에 의해 실행되는 작업 (실행 시점에 config.json 재로드)"""
    # 실행 시점에 config 재로드 → 재시작 없이 키워드/스케줄 변경 반영
    try:
        config = load_config()
        logger.info(f"[스케줄 실행] 키워드: {config.keywords}")
    except Exception as e:
        logger.error(f"config.json 로드 실패: {e}")
        return

    result = await run_automation()
    if result["success"]:
        logger.info(f"스케줄 작업 성공: {result['extended']}개 연장 완료")
    else:
        logger.error(
            f"스케줄 작업 부분 실패: 성공 {result['extended']}개 / 실패 {result['failed']}개"
        )


async def run_scheduler() -> None:
    """config/config.json 을 읽어 스케줄러를 시작합니다."""
    # 시작 시점에 config 로드 (스케줄 설정용)
    config = load_config()
    schedule = config.schedule

    logger.info("=" * 60)
    logger.info("스케줄러 시작")
    logger.info(f"실행 주기: {schedule.describe()}")
    logger.info(f"키워드: {config.keywords}")
    logger.info("종료하려면 Ctrl+C를 누르세요.")
    logger.info("=" * 60)

    trigger = build_cron_trigger(schedule)

    scheduler = AsyncIOScheduler(timezone=KST)
    scheduler.add_job(
        scheduled_job,
        trigger=trigger,
        id="auto_extend",
        name="그룹수업 종료일 자동 연장",
        replace_existing=True,
    )
    scheduler.start()

    # 다음 실행 예정 시간 출력
    for job in scheduler.get_jobs():
        logger.info(f"다음 실행 예정: {job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("스케줄러 종료")
        scheduler.shutdown()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="스튜디오메이트 그룹수업 종료일 자동 연장/롤백"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--run-now",
        action="store_true",
        help="스케줄을 기다리지 않고 즉시 1회 실행(연장)",
    )
    mode_group.add_argument(
        "--test-date",
        type=parse_test_date,
        metavar="YYYY-MM-DD",
        help="입력한 날짜를 실행일로 간주하여 DRY-RUN 테스트",
    )
    mode_group.add_argument(
        "--rollback",
        action="store_true",
        help="종료일을 1주일씩 롤백 (테스트용)"
    )
    args = parser.parse_args()

    if args.test_date:
        logger.info(f"특정 날짜 DRY-RUN 테스트 모드: {args.test_date}")
        result = await run_automation(
            execution_date=args.test_date,
            force_dry_run=True,
        )
        sys.exit(0 if result["success"] else 1)
    elif args.rollback:
        logger.info("롤백 모드")
        # result = await run_rollback()
        sys.exit(0 if result["success"] else 1)
    elif args.run_now:
        logger.info("즉시 실행 모드")
        result = await run_automation()
        sys.exit(0 if result["success"] else 1)
    else:
        await run_scheduler()


if __name__ == "__main__":
    asyncio.run(main())
