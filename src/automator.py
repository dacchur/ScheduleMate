import asyncio
from datetime import datetime
from pathlib import Path
from typing import List

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger

from src.pages.login_page import login
from src.pages.schedule_page import (
    go_to_schedule,
    set_current_week,
    set_group_class_filter,
    collect_matching_lecture_ids,
)
from src.pages.detail_page import navigate_to_detail, extend_end_date
from src.utils.config_loader import load_config


async def run_automation() -> dict:
    """
    전체 자동화 플로우를 실행합니다.

    반환값:
        {
            "success": bool,
            "total": int,        # 처리 시도한 수업 수
            "extended": int,     # 성공적으로 연장된 수업 수
            "failed": int,       # 실패한 수업 수
            "lecture_ids": list, # 처리한 ID 목록
        }
    """
    result = {
        "success": False,
        "total": 0,
        "extended": 0,
        "failed": 0,
        "lecture_ids": [],
    }

    # 설정 로드 (실행 시점마다 config.json 최신 값 반영)
    config = load_config()
    login_id = config.login_id
    password = config.login_password
    keywords = config.keywords
    headless = config.headless

    logger.info("=" * 60)
    logger.info(f"자동화 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"키워드: {keywords}")
    logger.info(f"헤드리스 모드: {headless}")
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
            await set_current_week(page)
            await set_group_class_filter(page)
            logger.info("일정 페이지 설정 완료 (현재 주 / 그룹수업 필터)")

            # ── Phase 3: 매칭 수업 ID 수집 ────────────────────────────────
            lecture_ids: List[str] = await collect_matching_lecture_ids(page, keywords)
            result["total"] = len(lecture_ids)
            result["lecture_ids"] = lecture_ids

            if not lecture_ids:
                logger.warning("연장할 수업이 없습니다.")
                result["success"] = True
                return result

            logger.info(f"총 {len(lecture_ids)}개 수업 연장 시작")

            # ── Phase 4: 각 수업 종료일 연장 ─────────────────────────────
            # 첫 연장 성공 시 target(새 종료일)을 기록 → 이미 target 이상인 수업은 skip
            target_end_date: str = None
            for idx, lecture_id in enumerate(lecture_ids, start=1):
                logger.info(f"[{idx}/{len(lecture_ids)}] 수업 ID: {lecture_id}")
                try:
                    await navigate_to_detail(page, lecture_id)
                    success, new_end_date = await extend_end_date(
                        page, lecture_id, target_end_date=target_end_date
                    )
                    if success:
                        result["extended"] += 1
                        if new_end_date and target_end_date is None:
                            target_end_date = new_end_date
                            logger.info(f"목표 종료일 설정: {target_end_date} (이후 수업은 이 날짜 미만일 때만 연장)")
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
    logger.info(f"자동화 완료: 성공 {result['extended']}개 / 실패 {result['failed']}개 / 총 {result['total']}개")
    logger.info("=" * 60)

    return result
