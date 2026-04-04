import asyncio
from playwright.async_api import Page
from loguru import logger

from src.utils.date_utils import add_one_week, is_date_before

BASE_URL = "https://foreumpilates.studiomate.kr"
DETAIL_URL = f"{BASE_URL}/lecture/detail"


async def navigate_to_detail(page: Page, lecture_id: str) -> None:
    """강좌 상세 페이지로 직접 이동합니다."""
    url = f"{DETAIL_URL}?id={lecture_id}"
    logger.info(f"상세 페이지 이동: {url}")
    await page.goto(url, wait_until="networkidle")

    # 로딩 마스크 대기
    try:
        await page.locator(".el-loading-mask").wait_for(state="hidden", timeout=10_000)
    except Exception:
        pass

    # Vue SPA가 h3를 빈 채로 먼저 렌더링하므로, 실제 작업 대상인 종료일변경 버튼이 나타날 때까지 대기
    await page.wait_for_selector(
        ".lecture-info__block__header__buttons button",
        timeout=15_000,
    )


async def get_course_title(page: Page) -> str:
    """상세 페이지 상단의 수업 제목을 반환합니다."""
    title_el = page.locator("h3").first
    return (await title_el.inner_text()).strip()


async def extend_end_date(page: Page, lecture_id: str, target_end_date: str = None) -> tuple:
    """
    강좌 상세 페이지에서 종료일을 1주일 연장합니다.

    target_end_date: 첫 번째 수업의 종료일 + 7일. 현재 종료일이 이 날짜 이상이면
                     이미 연장된 수업으로 보고 skip합니다.

    반환값: (성공 여부: bool, 새 목표 종료일: str | None)
             - 실제 연장된 경우: (True, new_end_date_str)
             - skip된 경우:      (True, None)
             - 실패한 경우:      (False, None)
    """
    title = await get_course_title(page)
    logger.info(f"[{lecture_id}] '{title}' 종료일 변경 시작")

    # ── 1. '종료일변경' 버튼 클릭 ─────────────────────────────────────────
    change_btn = page.locator(".lecture-info__block__header__buttons button").filter(
        has_text="종료일변경"
    )
    await change_btn.wait_for(state="visible", timeout=10_000)
    await change_btn.click()
    logger.debug("'종료일변경' 버튼 클릭")

    # ── 2. 모달 열림 대기 ──────────────────────────────────────────────────
    modal = page.locator("#change-course-end-date-dialog")
    await modal.wait_for(state="visible", timeout=8_000)
    logger.debug("종료일 변경 모달 열림 확인")

    # ── 3. '연장' 라디오 버튼 선택 확인 (기본값이므로 이미 선택되어 있음) ──
    extend_radio_label = modal.locator("label").filter(has_text="연장")
    is_active = "is-active" in (await extend_radio_label.get_attribute("class") or "")
    if not is_active:
        logger.debug("'연장' 라디오 버튼 수동 클릭")
        await extend_radio_label.click()
        await page.wait_for_timeout(400)
    else:
        logger.debug("'연장' 이미 선택된 상태")

    # ── 4. 현재 종료일 읽기 ────────────────────────────────────────────────
    # 표시 형식: "2026. 4. 5. 까지 기간을 연장하여..."
    message_el = modal.locator("p.change-course-end-date-dialog__message b").first
    current_end_date_str = (await message_el.inner_text()).strip()
    logger.info(f"[{lecture_id}] 현재 종료일: '{current_end_date_str}'")

    # ── 4-1. 이미 목표 날짜 이상이면 skip ────────────────────────────────────
    if target_end_date and not is_date_before(current_end_date_str, target_end_date):
        logger.info(f"[{lecture_id}] 종료일({current_end_date_str}) ≥ 목표({target_end_date}) → 건너뜀")
        await _close_modal(page, modal)
        return True, None

    # ── 5. 새로운 종료일 계산 (현재 종료일 + 7일) ──────────────────────────
    try:
        new_end_date_str = add_one_week(current_end_date_str)
    except ValueError as e:
        logger.error(f"[{lecture_id}] 날짜 계산 오류: {e}")
        await _close_modal(page, modal)
        return False, None
    logger.info(f"[{lecture_id}] 새로운 종료일: '{new_end_date_str}'")

    # ── 6. 새로운 종료일 입력 ──────────────────────────────────────────────
    # 날짜 입력 필드: .change-course-end-date-dialog__dates 내 두 번째 input
    dates_section = modal.locator(".change-course-end-date-dialog__dates")
    new_date_input = dates_section.locator("input.el-input__inner").nth(1)

    await new_date_input.click()
    await page.wait_for_timeout(400)

    # 전체 선택 후 새 날짜 입력
    await new_date_input.click(click_count=3)
    await new_date_input.type(new_end_date_str, delay=50)
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(500)

    # 입력 후 확인 메시지의 날짜가 변경되었는지 검증
    updated_date_str = (await message_el.inner_text()).strip()
    logger.debug(f"[{lecture_id}] 입력 후 표시 날짜: '{updated_date_str}'")

    # ── 7. '변경' 버튼 클릭 ────────────────────────────────────────────────
    change_confirm_btn = modal.locator("button.el-button--primary").filter(has_text="변경")
    await change_confirm_btn.click()
    logger.debug("'변경' 버튼 클릭")

    # ── 8. 2차 확인 다이얼로그 처리 ("계속 하시겠습니까?" → 확인) ────────────
    try:
        confirm_dialog = page.locator(".el-message-box")
        await confirm_dialog.wait_for(state="visible", timeout=5_000)
        logger.debug("확인 다이얼로그 감지 → '확인' 클릭")
        ok_btn = confirm_dialog.locator("button.el-button--primary")
        await ok_btn.click()
    except Exception:
        logger.debug("확인 다이얼로그 없음 → 건너뜀")

    # ── 9. 모달 닫힘 확인 ──────────────────────────────────────────────────
    try:
        await modal.wait_for(state="hidden", timeout=8_000)
        logger.info(f"[{lecture_id}] '{title}' 종료일 변경 완료: {current_end_date_str} → {new_end_date_str}")
        return True, new_end_date_str
    except Exception:
        logger.error(f"[{lecture_id}] 모달이 닫히지 않음 - 변경 실패 가능성 있음")
        await page.screenshot(path=f"screenshots/extend_failed_{lecture_id}.png")
        return False, None


async def _close_modal(page: Page, modal) -> None:
    """모달의 '취소' 버튼을 클릭하여 닫습니다."""
    try:
        cancel_btn = modal.locator("button.el-button--default").filter(has_text="취소")
        await cancel_btn.click()
        await modal.wait_for(state="hidden", timeout=5_000)
    except Exception:
        await page.keyboard.press("Escape")
