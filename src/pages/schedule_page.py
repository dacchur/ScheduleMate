import asyncio
from typing import List
from playwright.async_api import Page
from loguru import logger

BASE_URL = "https://foreumpilates.studiomate.kr"
SCHEDULE_URL = f"{BASE_URL}/schedule"


async def go_to_schedule(page: Page) -> None:
    """일정 페이지로 이동합니다."""
    logger.info("일정 페이지로 이동")
    await page.goto(SCHEDULE_URL, wait_until="networkidle")
    await page.wait_for_timeout(1000)  # 팝업이 뜰 시간을 위한 짧은 대기

    # 1. 공지사항 팝업 등이 있다면 닫기
    try:
        # '닫기' 또는 'X' 버튼 형태의 팝업 닫기 시도 (여러 패턴 대응)
        popups = page.locator(".el-dialog__wrapper:visible, .el-message-box__wrapper:visible")
        count = await popups.count()
        if count > 0:
            logger.info(f"팝업 {count}개 감지 → 닫기 시도")
            for i in range(count):
                popup = popups.nth(i)
                # '닫기' 텍스트를 가진 버튼 검색
                close_btn = popup.locator("button").filter(has_text="닫기")
                if await close_btn.count() > 0:
                    await close_btn.click()
                    await page.wait_for_timeout(500)
                else:
                    # 'X' 아이콘 버튼 검색 (Element UI 기본 클래스)
                    x_btn = popup.locator(".el-dialog__headerbtn, .el-message-box__headerbtn")
                    if await x_btn.count() > 0:
                        await x_btn.click()
                        await page.wait_for_timeout(500)
    except Exception as e:
        logger.debug(f"팝업 처리 중 예외 발생: {e}")

    # 2. 모든 'el-'로 시작하는 오버레이 요소들이 사라질 때까지 대기
    try:
        await page.locator(".el-loading-mask, .el-message-box__wrapper, .el-dialog__wrapper").wait_for(
            state="hidden", timeout=10_000
        )
    except Exception:
        pass

    await page.wait_for_selector(".calendar-controls__tabs", timeout=15_000)
    await page.wait_for_timeout(1000)  # 추가적인 안정성을 위한 대기
    logger.debug("일정 페이지 로드 완료")


async def set_current_week(page: Page) -> None:
    """
    현재 주간 뷰를 확보합니다.
    - '이번주' 버튼이 활성화 상태면 클릭하여 현재 주로 이동
    - 이미 비활성화(disabled) 상태면 현재 주이므로 그대로 진행
    """
    buttons_container = page.locator(".calendar-controls__buttons")
    await buttons_container.wait_for(state="visible")

    this_week_btn = buttons_container.locator("button").filter(has_text="이번주")
    is_disabled = await this_week_btn.get_attribute("disabled")
    if is_disabled is None:
        await this_week_btn.click(force=True)
        # 클릭 후 로딩 오버레이 대기
        try:
            await page.locator(".el-loading-mask, .el-message-box__wrapper, .el-dialog__wrapper").wait_for(
                state="hidden", timeout=10_000
            )
        except Exception:
            pass
        await page.wait_for_timeout(800)
        logger.debug("'이번주' 버튼 클릭 → 현재 주로 이동")
    else:
        logger.debug("이미 현재 주 → 이동 불필요")


async def set_group_class_filter(page: Page) -> None:
    """카테고리를 '그룹수업'으로 설정합니다."""
    # 로딩 중일 수 있으므로 대기
    try:
        # 모든 'el-'로 시작하는 오버레이 요소들이 사라질 때까지 대기 (로딩 마스크, 대화상자 등)
        await page.locator(".el-loading-mask, .el-message-box__wrapper, .el-dialog__wrapper").wait_for(
            state="hidden", timeout=10_000
        )
    except Exception:
        pass

    tabs = page.locator(".calendar-controls__tabs li")
    tab_count = await tabs.count()

    for i in range(tab_count):
        tab = tabs.nth(i)
        text = (await tab.inner_text()).strip()
        if "그룹수업" in text:
            # 강제 클릭(force=True) 옵션 추가 및 약간의 대기 후 시도
            await page.wait_for_timeout(500)
            await tab.click(force=True)
            # 탭 전환 후 캘린더가 다시 렌더링될 때까지 이벤트 대기
            try:
                await page.wait_for_selector(".event-item.el-popover__reference", timeout=5_000)
            except Exception:
                logger.warning("그룹수업 탭 전환 후 이벤트를 찾지 못했습니다 (수업이 없을 수 있음)")
            logger.debug("'그룹수업' 탭 클릭 완료")
            return

    logger.warning("'그룹수업' 탭을 찾지 못했습니다. 현재 필터 그대로 진행합니다.")


async def collect_matching_lecture_ids(page: Page, keywords: List[str]) -> List[str]:
    """
    현재 주간 뷰에서 키워드에 매칭되는 수업의 lecture ID 목록을 수집합니다.

    1) 모든 event-item의 텍스트를 클릭 없이 읽어 키워드 매칭 여부 확인
    2) 매칭된 이벤트는 href 속성에서 ID 직접 추출 (클릭 불필요)
       → href 없을 경우 클릭 → URL에서 ID 추출 → 뒤로 이동 (폴백)
    """
    lecture_ids: List[str] = []

    events = page.locator(".event-item.el-popover__reference")
    total = await events.count()
    logger.info(f"이벤트 총 {total}개 발견")

    for event_idx in range(total):
        event = events.nth(event_idx)
        event_text = (await event.inner_text()).strip()

        if not any(kw in event_text for kw in keywords):
            continue

        # ── href에서 직접 ID 추출 시도 (클릭 없이) ─────────────────────────
        lecture_id = await page.evaluate(
            """(el) => {
                const a = el.querySelector('a[href*="/lecture/detail"]')
                    || el.closest('a[href*="/lecture/detail"]');
                if (a) {
                    const match = a.href.match(/[?&]id=([^&]+)/);
                    return match ? match[1] : null;
                }
                return null;
            }""",
            await event.element_handle(),
        )

        if lecture_id:
            logger.info(f"[{event_idx}] href에서 ID 추출: {lecture_id}")
        else:
            # ── 폴백: 클릭 → URL에서 ID 추출 → 뒤로 이동 ─────────────────
            logger.info(f"[{event_idx}] href 없음 → 클릭으로 ID 수집")
            await page.mouse.move(400, 30)
            try:
                await page.wait_for_function(
                    "() => document.querySelectorAll('div[role=\"tooltip\"][aria-hidden=\"false\"]').length === 0",
                    timeout=1_000,
                )
            except Exception:
                pass
            await event.click()
            await page.wait_for_url("**/lecture/detail**", timeout=10_000)

            current_url = page.url
            if "/lecture/detail" not in current_url:
                logger.warning(f"[{event_idx}] 예상치 못한 URL: {current_url}")
                await page.go_back()
                await page.wait_for_url("**/schedule**", timeout=10_000)
                await page.wait_for_selector(".event-item.el-popover__reference", timeout=10_000)
                continue

            lecture_id = current_url.split("id=")[-1].split("&")[0]
            logger.info(f"[{event_idx}] 클릭으로 ID 수집: {lecture_id}")

            await page.go_back()
            await page.wait_for_url("**/schedule**", timeout=10_000)
            await page.wait_for_selector(".event-item.el-popover__reference", timeout=10_000)

        if lecture_id and lecture_id not in lecture_ids:
            lecture_ids.append(lecture_id)

    logger.info(f"수집 완료 - 연장 대상 수업 {len(lecture_ids)}개: {lecture_ids}")
    return lecture_ids
