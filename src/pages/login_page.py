import asyncio
from playwright.async_api import Page
from loguru import logger

BASE_URL = "https://foreumpilates.studiomate.kr"
LOGIN_URL = f"{BASE_URL}/login"
SCHEDULE_URL = f"{BASE_URL}/schedule"


async def login(page: Page, login_id: str, password: str) -> bool:
    """
    스튜디오메이트 로그인을 수행합니다.
    성공 시 True, 실패 시 False 반환.
    """
    logger.info(f"로그인 시도: {LOGIN_URL}")

    await page.goto(LOGIN_URL, wait_until="networkidle")

    # 아이디 입력 (#identity)
    await page.wait_for_selector("#identity", state="visible")
    await page.fill("#identity", login_id)
    logger.debug("아이디 입력 완료")

    # 비밀번호 입력 (#password)
    await page.fill("#password", password)
    logger.debug("비밀번호 입력 완료")

    # 로그인 버튼 클릭
    await page.click("button.success")
    logger.debug("로그인 버튼 클릭")

    # 로그인 성공 확인: /schedule 로 리다이렉트 대기
    try:
        await page.wait_for_url(f"{BASE_URL}/schedule**", timeout=15_000)
        logger.info("로그인 성공 - 일정 페이지로 이동 완료")
        return True
    except Exception:
        # 로그인 실패 시 현재 URL 및 에러 확인
        current_url = page.url
        logger.error(f"로그인 실패 - 현재 URL: {current_url}")
        await page.screenshot(path="screenshots/login_failed.png")
        return False
