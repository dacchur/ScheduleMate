import asyncio
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger

from src.pages.login_page import login
from src.pages.schedule_page import (
    go_to_schedule,
    set_week_for_date,
    set_previous_week,
    set_group_class_filter,
    collect_matching_lecture_ids,
)
from src.pages.detail_page import navigate_to_detail, extend_end_date, rollback_end_date
from src.utils.config_loader import load_config
from src.utils.date_utils import get_date_one_week_from_now, get_kst_today


async def _collect_target_lecture_ids(
    page: Page,
    keywords: List[str],
    range_start,
    range_end,
) -> List[str]:
    """이전 주와 현재 주에서 지정 날짜 범위의 수업 ID를 중복 없이 수집합니다."""
    current_week_ids = await collect_matching_lecture_ids(
        page,
        keywords,
        range_start,
        range_end,
    )

    await set_previous_week(page)
    previous_week_ids = await collect_matching_lecture_ids(
        page,
        keywords,
        range_start,
        range_end,
    )

    return list(dict.fromkeys(previous_week_ids + current_week_ids))


async def run_automation(
    execution_date: date | None = None,
    force_dry_run: bool = False,
) -> dict:
    """
    전체 자동화 플로우를 실행합니다.

    반환값:
        {
            "success": bool,
            "total": int,        # 처리 시도한 수업 수
            "extended": int,     # 성공적으로 연장된 수업 수
            "skipped": int,      # 기준 종료일 이후로 skip된 수업 수
            "failed": int,       # 실패한 수업 수
            "lecture_ids": list, # 처리한 ID 목록
        }
    """
    result = {
        "success": False,
        "total": 0,
        "extended": 0,
        "skipped": 0,
        "failed": 0,
        "lecture_ids": [],
    }

    # 설정 로드 (실행 시점마다 config.json 최신 값 반영)
    config = load_config()
    login_id = config.login_id
    password = config.login_password
    keywords = config.keywords
    headless = config.headless
    dry_run = config.dry_run or force_dry_run

    if execution_date is None:
        execution_date = get_kst_today()
    lecture_range_start = execution_date - timedelta(days=7)
    target_end_date = get_date_one_week_from_now(execution_date)

    logger.info("=" * 60)
    logger.info(f"자동화 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(
        f"연장 대상 수업일: {lecture_range_start} ~ {execution_date} (양 끝 포함)"
    )
    logger.info(f"기준 종료일: {target_end_date} (실행일 + 1주일)")
    logger.info(f"키워드: {keywords}")
    logger.info(f"헤드리스 모드: {headless}")
    if dry_run:
        logger.info("DRY-RUN 모드 : 실제 업데이트 없이 연장될 날짜만 확인합니다.")
    if force_dry_run:
        logger.info(f"TEST 날짜 모드: {execution_date}")
    logger.info("=" * 60)

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page: Page = await context.new_page()

        try:
            # ── Phase 1: 로그인 ───────────────────────────────────────────
            logged_in = await login(page, login_id, password)
            if not logged_in:
                logger.error("로그인 실패 - 자동화 중단")
                return result

            # ── Phase 2: 일정 페이지 설정 ─────────────────────────────────
            await go_to_schedule(page)
            await set_week_for_date(page, execution_date)
            await set_group_class_filter(page)
            logger.info(
                f"일정 페이지 설정 완료 "
                f"(기준일 {execution_date} / UI 카테고리: 그룹수업 / "
                f"제목 키워드: {keywords})"
            )

            # ── Phase 3: 이전 주와 현재 주에서 매칭 수업 ID 수집 ──────────
            lecture_ids = await _collect_target_lecture_ids(
                page,
                keywords,
                lecture_range_start,
                execution_date,
            )
            result["total"] = len(lecture_ids)
            result["lecture_ids"] = lecture_ids

            if not lecture_ids:
                logger.warning("연장할 수업이 없습니다.")
                result["success"] = True
                return result

            logger.info(f"총 {len(lecture_ids)}개 수업 연장 시작")

            # ── Phase 4: 각 수업 종료일 연장 ─────────────────────────────
            # 모든 수업을 기준 종료일로 맞춤
            for idx, lecture_id in enumerate(lecture_ids, start=1):
                logger.info(f"[{idx}/{len(lecture_ids)}] 수업 ID: {lecture_id}")
                try:
                    await navigate_to_detail(page, lecture_id)
                    success, new_end_date = await extend_end_date(page, lecture_id, target_end_date, dry_run=dry_run)
                    if success:
                        if new_end_date is None:
                            result["skipped"] += 1
                        else:
                            result["extended"] += 1
                    else:
                        result["failed"] += 1
                except Exception as e:
                    logger.error(f"[{lecture_id}] 연장 중 예외 발생: {e}")
                    await page.screenshot(
                        path=f"screenshots/error_{lecture_id}_{idx}.png"
                    )
                    result["failed"] += 1

            result["success"] = result["failed"] == 0

        except Exception as e:
            logger.error(f"자동화 중 예외 발생: {e}")
            await page.screenshot(path="screenshots/critical_error.png")

        finally:
            await context.close()
            await browser.close()

    logger.info("=" * 60)
    logger.info(f"자동화 완료: 성공 {result['extended']}개 / skip {result['skipped']}개 / 실패 {result['failed']}개 / 총 {result['total']}개")
    logger.info("=" * 60)

    return result


async def run_rollback() -> dict:
    """
    전체 롤백 플로우를 실행합니다.

    반환값:
        {
            "success": bool,
            "total": int,        # 처리 시도한 수업 수
            "rolled_back": int,     # 성공적으로 연장된 수업 수
            "failed": int,       # 실패한 수업 수
            "lecture_ids": list, # 처리한 ID 목록
        }
    """
    result = {
        "success": False,
        "total": 0,
        "rolled_back": 0,
        "failed": 0,
        "lecture_ids": [],
    }

    # 설정 로드 (실행 시점마다 config.json 최신 값 반영)
    config = load_config()
    login_id = config.login_id
    password = config.login_password
    keywords = config.keywords
    headless = config.headless
    dry_run = config.dry_run
    execution_date = get_kst_today()
    lecture_range_start = execution_date - timedelta(days=7)

    logger.info("=" * 60)
    logger.info(f"롤백 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"키워드: {keywords}")
    logger.info(f"헤드리스 모드: {headless}")
    if dry_run:
        logger.info("DRY-RUN 모드 : 실제 업데이트 없이 연장될 날짜만 확인합니다.")
    logger.info("=" * 60)

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page: Page = await context.new_page()

        try:
            # ── Phase 1: 로그인 ───────────────────────────────────────────
            logged_in = await login(page, login_id, password)
            if not logged_in:
                logger.error("로그인 실패 - 롤백 중단")
                return result

            # ── Phase 2: 일정 페이지 설정 ─────────────────────────────────
            await go_to_schedule(page)
            await set_week_for_date(page, execution_date)
            await set_group_class_filter(page)
            logger.info(
                f"일정 페이지 설정 완료 "
                f"(기준일 {execution_date} / UI 카테고리: 그룹수업 / "
                f"제목 키워드: {keywords})"
            )

            # ── Phase 3: 이전 주와 현재 주에서 매칭 수업 ID 수집 ──────────
            lecture_ids = await _collect_target_lecture_ids(
                page,
                keywords,
                lecture_range_start,
                execution_date,
            )
            result["total"] = len(lecture_ids)
            result["lecture_ids"] = lecture_ids

            if not lecture_ids:
                logger.warning("롤백할 수업이 없습니다.")
                result["success"] = True
                return result

            logger.info(f"총 {len(lecture_ids)}개 수업 롤백 시작")

            # ── Phase 4: 각 수업 종료일 롤백 ─────────────────────────────
            for idx, lecture_id in enumerate(lecture_ids, start=1):
                logger.info(f"[{idx}/{len(lecture_ids)}] 수업 ID: {lecture_id}")
                try:
                    await navigate_to_detail(page, lecture_id)
                    success, new_end_date = await rollback_end_date(page, lecture_id, dry_run=dry_run)
                    if success:
                        result["rolled_back"] += 1
                    else:
                        result["failed"] += 1
                except Exception as e:
                    logger.error(f"[{lecture_id}] 롤백 중 예외 발생: {e}")
                    await page.screenshot(
                        path=f"screenshots/rollback_error_{lecture_id}_{idx}.png"
                    )
                    result["failed"] += 1

            result["success"] = result["failed"] == 0

        except Exception as e:
            logger.error(f"롤백 중 예외 발생: {e}")
            await page.screenshot(path="screenshots/critical_rollback_error.png")

        finally:
            await context.close()
            await browser.close()

    logger.info("=" * 60)
    logger.info(f"롤백 완료: 성공 {result['rolled_back']}개 / 실패 {result['failed']}개 / 총 {result['total']}개")
    logger.info("=" * 60)

    return result
