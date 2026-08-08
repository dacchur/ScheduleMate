import asyncio
import re
from datetime import date, datetime
from typing import List
from zoneinfo import ZoneInfo
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
    buttons_container = page.locator(".calendar-controls__buttons:visible").first
    await buttons_container.wait_for(state="visible")

    this_week_btn = buttons_container.locator("button:visible").filter(
        has_text="이번주"
    ).first
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


async def set_previous_week(page: Page) -> None:
    """현재 주간 뷰에서 바로 이전 주로 이동합니다."""
    await _move_week(page, -1)


async def _move_week(page: Page, direction: int) -> None:
    """달력을 한 주 이전(-1) 또는 다음(+1)으로 이동합니다."""
    buttons_container = page.locator(".calendar-controls__buttons:visible").first
    await buttons_container.wait_for(state="visible")

    # 달력 컨트롤은 [이전 주, 이번주, 다음 주] 순서로 구성됩니다.
    buttons = buttons_container.locator("button:visible")
    button_count = await buttons.count()
    this_week_index = None
    for index in range(button_count):
        button = buttons.nth(index)
        if "이번주" in (await button.inner_text()).strip():
            this_week_index = index
            break

    if this_week_index is None:
        raise RuntimeError("달력에서 '이번주' 버튼을 찾을 수 없습니다.")

    target_index = this_week_index - 1 if direction < 0 else this_week_index + 1
    if not 0 <= target_index < button_count:
        raise RuntimeError(
            f"달력 이동 버튼 위치가 올바르지 않습니다: "
            f"이번주={this_week_index}, 대상={target_index}, 전체={button_count}"
        )

    target_button = buttons.nth(target_index)
    await target_button.wait_for(state="visible", timeout=5_000)
    await target_button.click()
    try:
        await page.locator(
            ".el-loading-mask, .el-message-box__wrapper, .el-dialog__wrapper"
        ).wait_for(state="hidden", timeout=10_000)
    except Exception:
        pass
    await page.wait_for_timeout(800)
    logger.debug("이전 주로 이동" if direction < 0 else "다음 주로 이동")


async def set_week_for_date(page: Page, target_date: date) -> None:
    """달력을 target_date가 속한 주로 이동합니다."""
    await set_current_week(page)

    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    current_week_start = date.fromordinal(today.toordinal() - today.weekday())
    target_week_start = date.fromordinal(
        target_date.toordinal() - target_date.weekday()
    )
    week_offset = (target_week_start - current_week_start).days // 7

    direction = -1 if week_offset < 0 else 1
    for _ in range(abs(week_offset)):
        await _move_week(page, direction)

    logger.info(f"기준 날짜가 속한 주로 이동 완료: {target_date}")


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


def _parse_event_date(event_date_str: str, reference_date: date) -> date:
    """
    일정 이벤트의 날짜를 파싱합니다.

    화면에 연도가 없으면 실행일과 가장 가까운 연도를 선택하여
    연말/연초를 걸친 최근 7일 범위도 처리합니다.
    """
    numbers = [int(value) for value in re.findall(r"\d+", event_date_str)]
    if len(numbers) >= 3:
        return date(numbers[0], numbers[1], numbers[2])
    if len(numbers) != 2:
        raise ValueError(f"날짜 파싱 실패: '{event_date_str}'")

    month, day = numbers
    candidates = [
        date(year, month, day)
        for year in (
            reference_date.year - 1,
            reference_date.year,
            reference_date.year + 1,
        )
    ]
    return min(candidates, key=lambda candidate: abs(candidate - reference_date))


async def _get_event_date_str(page: Page, event) -> str | None:
    """이벤트가 속한 캘린더 셀의 날짜 속성을 읽습니다."""
    return await page.evaluate(
        """(event) => {
            const structuredDate = (value) => {
                if (!value) return null;
                const text = String(value);
                const fullMatch = text.match(
                    /(?:^|\\D)(\\d{4})[-./](\\d{1,2})[-./](\\d{1,2})(?:\\D|$)/
                );
                if (fullMatch) {
                    return `${fullMatch[1]}.${fullMatch[2]}.${fullMatch[3]}`;
                }

                // 날짜 용도가 명확한 속성에 한해서만 월/일 형식을 허용합니다.
                const shortMatch = text.match(
                    /^\\s*(\\d{1,2})[-./]\\s*(\\d{1,2})[-./]?\\s*$/
                );
                return shortMatch ? `${shortMatch[1]}.${shortMatch[2]}` : null;
            };

            const dateAttributes = [
                "data-date", "data-start", "data-start-date",
                "datetime", "date"
            ];

            // 가장 신뢰할 수 있는 경우: 이벤트 또는 상위 날짜 셀에
            // YYYY-MM-DD 형태의 날짜 속성이 있는 경우
            for (let node = event; node; node = node.parentElement) {
                for (const name of dateAttributes) {
                    const parsed = structuredDate(node.getAttribute(name));
                    if (parsed) return parsed;
                }
            }

            // 날짜 헤더와 이벤트 영역이 별도 DOM인 달력 대응:
            // 이벤트의 가로 중심점과 겹치는 data-date 셀을 찾습니다.
            const eventRect = event.getBoundingClientRect();
            const eventCenterX = eventRect.left + eventRect.width / 2;
            const candidates = [];
            for (const node of document.querySelectorAll(
                "[data-date], [data-start], [data-start-date], [datetime]"
            )) {
                let parsed = null;
                for (const name of dateAttributes) {
                    parsed = structuredDate(node.getAttribute(name));
                    if (parsed) break;
                }
                if (!parsed) continue;

                const rect = node.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) continue;
                if (rect.left <= eventCenterX && eventCenterX <= rect.right) {
                    candidates.push({
                        date: parsed,
                        distance: Math.abs(
                            rect.left + rect.width / 2 - eventCenterX
                        ),
                    });
                }
            }

            candidates.sort((a, b) => a.distance - b.distance);
            return candidates.length ? candidates[0].date : null;
        }""",
        await event.element_handle(),
    )


async def collect_matching_lecture_ids(
    page: Page,
    keywords: List[str],
    range_start: date,
    range_end: date,
) -> List[str]:
    """
    현재 표시된 주간 뷰에서 날짜 범위와 키워드에 매칭되는 수업 ID를 수집합니다.

    1) 모든 event-item의 텍스트를 클릭 없이 읽어 키워드 매칭 여부 확인
    2) range_start <= 수업일 <= range_end 인지 확인
    3) 매칭된 이벤트는 href 속성에서 ID 직접 추출 (클릭 불필요)
       → href 없을 경우 클릭 → URL에서 ID 추출 → 뒤로 이동 (폴백)
    """
    lecture_ids: List[str] = []

    events = page.locator(".event-item.el-popover__reference")
    total = await events.count()
    logger.info(f"이벤트 총 {total}개 발견")

    for event_idx in range(total):
        event = events.nth(event_idx)
        event_text = (await event.inner_text()).strip()

        event_date_str = await _get_event_date_str(page, event)
        if not event_date_str:
            logger.warning(
                f"[{event_idx}] 캘린더 셀에서 날짜를 찾을 수 없음: "
                f"{event_text[:80]}..."
            )
            continue

        try:
            event_date = _parse_event_date(event_date_str, range_end)
        except ValueError as e:
            logger.warning(f"[{event_idx}] {e}")
            continue

        logger.debug(f"[{event_idx}] 이벤트 날짜: {event_date}")
        if not range_start <= event_date <= range_end:
            logger.debug(
                f"[{event_idx}] 대상 기간 밖 수업 → 제외 "
                f"({range_start} ~ {range_end})"
            )
            continue

        if not any(keyword in event_text for keyword in keywords):
            continue

        logger.info(f"[{event_idx}] 키워드 일치 수업: '{event_text[:80]}'")
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

            # 열려있는 popover가 있는지 확인하고 있으면 ESC로 닫기
            has_open_popover = await page.evaluate(
                "() => document.querySelectorAll('div[role=\"tooltip\"][aria-hidden=\"false\"]').length > 0"
            )
            if has_open_popover:
                logger.debug(f"[{event_idx}] 열려있는 popover 감지 -> ESC로 닫기")
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(300)

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
