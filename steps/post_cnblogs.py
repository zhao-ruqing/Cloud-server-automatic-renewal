# -*- coding: utf-8 -*-
"""CNBlogs publish flow."""

import logging
import os
import re
from pathlib import Path
from typing import Any

import pyperclip
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.browser import BrowserSession, launch_browser
from utils.logger import log_artifact_path
from utils.notify import send_cnblogs_failure_email
from utils.selectors import CNBLOGS
from utils.viewport import random_viewport

logger = logging.getLogger("sanfeng")

_ARTICLE_URL_RE = re.compile(r"https://www\.cnblogs\.com/[^/]+/articles/\d+")
_PAGE_ERROR_SELECTORS = (".mat-error", ".error-message", '[role="alert"]')


class CnblogsPostError(Exception):
    pass


class CnblogsLoginError(CnblogsPostError):
    pass


def _is_login_page(page) -> bool:
    url = page.url.lower()
    if CNBLOGS["login_url_contains"] in url:
        return True
    username = page.locator(CNBLOGS["username"])
    return username.count() > 0 and username.first.is_visible()


def _collect_page_errors(page) -> str:
    errors: list[str] = []
    for selector in _PAGE_ERROR_SELECTORS:
        locator = page.locator(selector)
        for index in range(min(locator.count(), 5)):
            try:
                text = locator.nth(index).inner_text(timeout=500).strip()
            except PlaywrightTimeoutError:
                continue
            if text and text not in errors:
                errors.append(text)
    return "; ".join(errors)


def _failure_screenshot(page, filename: str) -> Path:
    path = log_artifact_path(filename)
    page.screenshot(path=str(path), full_page=False)
    return path


def _notify_failure(
    config: dict[str, Any],
    *,
    failure_type: str,
    reason: str,
    page=None,
    screenshot_path: Path | str | None = None,
    provider: str | None = None,
    article_title: str | None = None,
) -> None:
    page_url = page.url if page else ""
    page_errors = _collect_page_errors(page) if page else ""

    if screenshot_path is None and page is not None:
        filename = (
            "cnblogs_login_failed.png"
            if failure_type == "login"
            else "cnblogs_post_failed.png"
        )
        screenshot_path = _failure_screenshot(page, filename)

    send_cnblogs_failure_email(
        config,
        failure_type=failure_type,
        reason=reason,
        page_url=page_url,
        page_errors=page_errors,
        screenshot_path=screenshot_path,
        provider=provider,
        article_title=article_title,
    )


def _resolve_credentials(cnblogs_cfg: dict[str, Any]) -> tuple[str, str]:
    username = os.environ.get(cnblogs_cfg.get("username_env", "CNBLOGS_USERNAME"), "").strip()
    password = os.environ.get(cnblogs_cfg.get("password_env", "CNBLOGS_PASSWORD"), "").strip()
    if not username or not password:
        raise CnblogsLoginError(
            "CNBlogs credentials empty. Set CNBLOGS_USERNAME/CNBLOGS_PASSWORD in .env "
            "or run: python scripts/init_cnblogs_auth.py"
        )
    return username, password


def _do_login(page, cnblogs_cfg: dict[str, Any]) -> None:
    username_input = page.locator(CNBLOGS["username"])
    password_input = page.locator(CNBLOGS["password"])
    username_input.wait_for(state="visible", timeout=15000)

    if username_input.input_value().strip() == "":
        username, password = _resolve_credentials(cnblogs_cfg)
        username_input.fill(username)
        password_input.fill(password)
    elif password_input.input_value().strip() == "":
        _, password = _resolve_credentials(cnblogs_cfg)
        password_input.fill(password)

    page.locator(CNBLOGS["login_btn"]).first.click()
    page.wait_for_timeout(int(cnblogs_cfg.get("login_wait_sec", 3) * 1000))
    try:
        page.wait_for_function(
            "() => !window.location.href.includes('account.cnblogs.com/signin')",
            timeout=30000,
        )
    except PlaywrightTimeoutError as exc:
        _failure_screenshot(page, "cnblogs_login_failed.png")
        raise CnblogsLoginError(
            "CNBlogs login timeout (captcha may be required)"
        ) from exc


def _ensure_logged_in(page, cnblogs_cfg: dict[str, Any]) -> None:
    if _is_login_page(page):
        logger.info("CNBlogs login required")
        _do_login(page, cnblogs_cfg)


def _fill_title(page, title: str) -> None:
    locator = page.locator(CNBLOGS["title_input"])
    locator.wait_for(state="visible", timeout=20000)
    locator.click()
    locator.fill("")
    locator.fill(title)
    page.wait_for_timeout(500)


def _fill_body(page, body: str) -> None:
    editor = page.locator(CNBLOGS["body_editor"])
    editor.wait_for(state="visible", timeout=20000)
    editor.click()
    pyperclip.copy(body)
    page.keyboard.press("Control+A")
    page.keyboard.press("Control+V")
    page.wait_for_timeout(800)


def _ensure_publish_checked(page) -> None:
    checkbox = page.locator(CNBLOGS["publish_checkbox"])
    if checkbox.count() == 0:
        return
    if not checkbox.is_checked():
        checkbox.check(force=True)
        page.wait_for_timeout(300)


def _click_publish(page, after_delay_sec: float) -> None:
    publish = page.locator(CNBLOGS["publish_btn"])
    publish.wait_for(state="visible", timeout=15000)
    publish.first.click()
    page.wait_for_timeout(int(after_delay_sec * 1000))


def _wait_after_publish(page, timeout_sec: int) -> None:
    try:
        page.wait_for_function(
            """
            () => {
              const saved = document.querySelector('[data-el-locator="post-saved-page"]');
              const path = window.location.pathname || '';
              const onArticles = path.includes('/articles') && !path.includes('/edit');
              return saved || onArticles;
            }
            """,
            timeout=timeout_sec * 1000,
        )
    except PlaywrightTimeoutError as exc:
        _failure_screenshot(page, "cnblogs_publish_timeout.png")
        raise CnblogsPostError(f"publish timeout ({timeout_sec}s)") from exc


def _navigate_to_published_article(page, title: str) -> None:
    """Click the just-published article to open public detail page."""
    saved_page = page.locator(CNBLOGS["saved_page"])
    if saved_page.count() > 0:
        link = page.locator(CNBLOGS["saved_title_link"]).first
        if link.count() == 0:
            link = page.locator(CNBLOGS["saved_view_link"]).first
        if link.count() > 0:
            link.click()
            page.wait_for_url("**/www.cnblogs.com/**/articles/**", timeout=30000)
            return

    link = page.get_by_role("link", name=title, exact=True).first
    try:
        link.wait_for(state="visible", timeout=15000)
        link.click()
        page.wait_for_url("**/www.cnblogs.com/**/articles/**", timeout=30000)
        return
    except PlaywrightTimeoutError:
        pass

    fallback = page.locator(f'a[href*="/articles/"]:has-text("{title}")').first
    if fallback.count() > 0:
        fallback.click()
        page.wait_for_url("**/www.cnblogs.com/**/articles/**", timeout=30000)
        return

    _failure_screenshot(page, "cnblogs_article_link_not_found.png")
    raise CnblogsPostError(f"published article link not found for title: {title}")


def _normalize_article_url(url: str) -> str:
    cleaned = url.split("?")[0].split("#")[0].rstrip("/")
    if _ARTICLE_URL_RE.match(cleaned):
        return cleaned
    match = re.search(r"(https://www\.cnblogs\.com/[^/]+/articles/\d+)", cleaned)
    if match:
        return match.group(1)
    raise CnblogsPostError(f"invalid cnblogs article url: {url}")


def _screenshot_article_page(
    page,
    screenshot_path: Path,
    browser_cfg: dict[str, Any],
) -> tuple[str, dict[str, int]]:
    final_url = _normalize_article_url(page.url)
    viewport = random_viewport(browser_cfg)
    page.set_viewport_size(viewport)
    page.wait_for_timeout(1000)
    page.locator(CNBLOGS["article_title"]).first.wait_for(state="visible", timeout=20000)
    page.screenshot(path=str(screenshot_path), full_page=False)
    return final_url, viewport


def _handle_post_failure(
    exc: Exception,
    *,
    config: dict[str, Any],
    page,
    provider: str | None,
    article_title: str,
) -> None:
    if isinstance(exc, CnblogsLoginError):
        failure_type = "login"
    elif isinstance(exc, CnblogsPostError):
        failure_type = "post"
    else:
        failure_type = "post"

    screenshot_path: Path | str | None = None
    if isinstance(exc, CnblogsPostError) and "publish timeout" in str(exc):
        screenshot_path = log_artifact_path("cnblogs_publish_timeout.png")
    elif isinstance(exc, CnblogsPostError) and "published article link not found" in str(exc):
        screenshot_path = log_artifact_path("cnblogs_article_link_not_found.png")
    elif isinstance(exc, CnblogsLoginError):
        screenshot_path = log_artifact_path("cnblogs_login_failed.png")

    _notify_failure(
        config,
        failure_type=failure_type,
        reason=str(exc),
        page=page,
        screenshot_path=screenshot_path,
        provider=provider,
        article_title=article_title,
    )


def post_cnblogs(
    title: str,
    body: str,
    config: dict[str, Any],
    output_dir: Path,
    screenshot_name: str = "article.png",
    provider: str | None = None,
) -> dict[str, str]:
    cnblogs_cfg = config["cnblogs"]
    browser_cfg = config["browser"]
    session: BrowserSession | None = None
    page = None

    try:
        session = launch_browser(
            browser_cfg,
            auth_state=cnblogs_cfg["auth_state"],
            profile_subdir=cnblogs_cfg.get("profile_dir", "cnblogs_profile"),
        )
        page = session.page
        page.goto(cnblogs_cfg["edit_url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        _ensure_logged_in(page, cnblogs_cfg)

        if _is_login_page(page):
            raise CnblogsLoginError("CNBlogs still on login page after auto login")

        page.goto(cnblogs_cfg["edit_url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        _fill_title(page, title)
        _fill_body(page, body)
        _ensure_publish_checked(page)
        _click_publish(page, cnblogs_cfg.get("after_publish_delay_sec", 2))
        _wait_after_publish(page, cnblogs_cfg.get("publish_timeout_sec", 60))

        _navigate_to_published_article(page, title)
        logger.info("Article detail URL: %s", page.url)

        screenshot_path = output_dir / screenshot_name
        final_url, screenshot_viewport = _screenshot_article_page(
            page, screenshot_path, browser_cfg
        )
        logger.info("Screenshot page URL: %s", final_url)

        return {
            "url": final_url,
            "screenshot_path": str(screenshot_path),
            "screenshot_viewport": screenshot_viewport,
        }
    except (CnblogsLoginError, CnblogsPostError) as exc:
        _handle_post_failure(
            exc,
            config=config,
            page=page,
            provider=provider,
            article_title=title,
        )
        raise
    except Exception as exc:
        wrapped = CnblogsPostError(str(exc))
        _handle_post_failure(
            wrapped,
            config=config,
            page=page,
            provider=provider,
            article_title=title,
        )
        raise wrapped from exc
    finally:
        if session:
            session.save_state(cnblogs_cfg["auth_state"])
            session.close()
