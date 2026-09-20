# -*- coding: utf-8 -*-
"""Shared cloud renewal: login, read expiry, fill renewal form."""

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.browser import BrowserSession, launch_browser
from utils.expiry_scheduler import parse_expiry_after_label, parse_expiry_datetime
from utils.logger import log_artifact_path
from utils.selectors import CLOUD

logger = logging.getLogger("sanfeng")


class CloudRenewalError(Exception):
    pass


def _is_login_page(page: Page) -> bool:
    if "/login" in page.url.lower():
        return True
    login_btn = page.locator(CLOUD["login_btn"])
    return login_btn.count() > 0 and login_btn.first.is_visible()


def _resolve_credentials(provider_cfg: dict[str, Any], provider: str) -> tuple[str, str]:
    username = os.environ.get(provider_cfg.get("username_env", ""), "").strip()
    password = os.environ.get(provider_cfg.get("password_env", ""), "").strip()
    if not username or not password:
        raise CloudRenewalError(
            f"{provider} credentials empty. Set "
            f"{provider_cfg.get('username_env')} / {provider_cfg.get('password_env')} in .env"
        )
    return username, password


def _open_login_page(page: Page, login_url: str) -> None:
    page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)


def _do_logout(page: Page, login_url: str, provider: str) -> None:
    """Expand the header user menu and click 安全退出, then return to login URL."""
    if _is_login_page(page):
        return

    user_menu = page.locator(CLOUD["user_menu"]).first
    try:
        user_menu.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeoutError:
        logger.warning("[%s] user menu not found, opening login URL", provider)
        _open_login_page(page, login_url)
        return

    logger.info("[%s] logout via header user menu", provider)
    user_menu.click()
    page.wait_for_timeout(400)
    logout_link = page.locator(CLOUD["logout_link"]).first
    try:
        logout_link.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError:
        user_menu.hover()
        page.wait_for_timeout(400)
        logout_link.wait_for(state="visible", timeout=5000)
    logout_link.click()

    try:
        page.wait_for_function(
            "() => window.location.href.toLowerCase().includes('/login')",
            timeout=15000,
        )
    except PlaywrightTimeoutError:
        logger.warning("[%s] logout did not reach login page, navigating", provider)
        _open_login_page(page, login_url)
        return
    page.wait_for_timeout(1000)


def _do_login(page: Page, provider_cfg: dict[str, Any], provider: str) -> None:
    username, password = _resolve_credentials(provider_cfg, provider)
    login_btn = page.locator(CLOUD["login_btn"])
    login_btn.wait_for(state="visible", timeout=15000)

    user_input = page.locator(CLOUD["username"]).first
    pass_input = page.locator(CLOUD["password"]).first
    user_input.wait_for(state="visible", timeout=15000)
    user_input.click()
    user_input.fill(username)
    pass_input.click()
    pass_input.fill(password)
    page.wait_for_timeout(200)
    user_input.fill(username)
    pass_input.fill(password)

    logger.info("[%s] login as %s", provider, username)
    login_btn.click()
    page.wait_for_timeout(int(provider_cfg.get("login_wait_sec", 2) * 1000))
    try:
        page.wait_for_function(
            "() => !window.location.href.toLowerCase().includes('/login')",
            timeout=30000,
        )
    except PlaywrightTimeoutError as exc:
        page.screenshot(path=str(log_artifact_path(f"{provider}_login_failed.png")), full_page=False)
        raise CloudRenewalError(f"{provider} login timeout") from exc


def login_cloud_account(page: Page, provider_cfg: dict[str, Any], provider: str) -> None:
    """If already logged in, logout first, then fill this account on the login page."""
    login_url = provider_cfg["login_url"]
    logger.info("[%s] open login: %s", provider, login_url)
    _open_login_page(page, login_url)
    if not _is_login_page(page):
        _do_logout(page, login_url, provider)
        if not _is_login_page(page):
            _open_login_page(page, login_url)
    _do_login(page, provider_cfg, provider)


def _parse_expiry_once(page: Page) -> datetime | None:
    label = CLOUD["expiry_label"]

    # Prefer datetime immediately after the "expiry" label (not "created at").
    body_text = page.locator("body").inner_text()
    expiry = parse_expiry_after_label(body_text, label)
    if expiry:
        return expiry

    labels = page.get_by_text(label, exact=False)
    for i in range(labels.count()):
        item = labels.nth(i)
        try:
            next_col = item.locator(
                "xpath=ancestor::div[contains(@class,'el-col')][1]"
                "/following-sibling::div[contains(@class,'el-col')][1]"
            )
            if next_col.count() > 0:
                expiry = parse_expiry_datetime(next_col.first.inner_text(timeout=3000))
                if expiry:
                    return expiry
        except Exception:
            continue
    return None


def read_expiry_from_page(page: Page, timeout_sec: float = 30) -> datetime:
    """Wait until the expiry datetime is rendered, then parse it."""
    deadline = time.monotonic() + max(float(timeout_sec), 0)
    waiting_logged = False
    while True:
        expiry = _parse_expiry_once(page)
        if expiry:
            logger.info(
                "Parsed expiry after label: %s",
                expiry.strftime("%Y-%m-%d %H:%M:%S"),
            )
            return expiry
        if time.monotonic() >= deadline:
            break
        if not waiting_logged:
            logger.info(
                "Expiry datetime not ready yet, waiting up to %.0fs",
                timeout_sec,
            )
            waiting_logged = True
        page.wait_for_timeout(500)

    page.screenshot(path=str(log_artifact_path("expiry_not_found.png")), full_page=False)
    raise CloudRenewalError("Expiry datetime not found after label")


def fetch_cloud_expiry(provider_cfg: dict[str, Any], browser_cfg: dict[str, Any], provider: str) -> datetime:
    session: BrowserSession | None = None
    try:
        session = launch_browser(
            browser_cfg,
            auth_state=provider_cfg.get("auth_state"),
            profile_subdir=provider_cfg.get("profile_dir"),
        )
        page = session.page
        login_cloud_account(page, provider_cfg, provider)

        server_url = provider_cfg["server_url"]
        page.goto(server_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(int(provider_cfg.get("form_load_wait_sec", 3) * 1000))
        expiry = read_expiry_from_page(
            page,
            timeout_sec=provider_cfg.get("expiry_load_timeout_sec", 30),
        )
        try:
            _do_logout(page, provider_cfg["login_url"], provider)
        except Exception as exc:
            logger.warning("[%s] logout after expiry check failed: %s", provider, exc)
        session.save_state(provider_cfg["auth_state"])
        return expiry
    finally:
        if session:
            session.close()


def _open_renewal_form(page: Page) -> None:
    url_input = page.locator(CLOUD["url_input"])
    if url_input.count() > 0 and url_input.first.is_visible():
        return

    nav_btn = page.locator(CLOUD["nav_extend_btn"]).first
    try:
        nav_btn.wait_for(state="visible", timeout=15000)
        nav_btn.click()
        page.wait_for_timeout(1500)
    except PlaywrightTimeoutError:
        logger.warning("Nav extend button not found, trying tab")

    if url_input.count() > 0 and url_input.first.is_visible():
        return

    tab = page.locator(CLOUD["extend_tab"])
    if tab.count() > 0 and tab.first.is_visible():
        tab.first.click()
        page.wait_for_timeout(1000)

    url_input.first.wait_for(state="visible", timeout=15000)


def _fill_renewal_form(page: Page, screenshot_path: Path, zhihu_url: str) -> None:
    _open_renewal_form(page)
    url_input = page.locator(CLOUD["url_input"]).first
    url_input.click()
    url_input.fill("")
    url_input.fill(zhihu_url)
    page.wait_for_timeout(500)

    file_input = page.locator(CLOUD["file_input"])
    if file_input.count() == 0:
        raise CloudRenewalError("File input #fileImg1 not found")
    file_input.set_input_files(str(screenshot_path))
    page.wait_for_timeout(1500)


def submit_cloud_renewal(
    provider: str,
    screenshot_path: str | Path,
    zhihu_url: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    provider_cfg = config.get(provider, {})
    if not provider_cfg.get("enabled"):
        return {"skipped": True, "provider": provider}

    screenshot_path = Path(screenshot_path)
    if not screenshot_path.exists():
        raise CloudRenewalError(f"Screenshot not found: {screenshot_path}")

    browser_cfg = config["browser"]
    session: BrowserSession | None = None

    try:
        session = launch_browser(
            browser_cfg,
            auth_state=provider_cfg.get("auth_state"),
            profile_subdir=provider_cfg.get("profile_dir"),
        )
        page = session.page
        login_cloud_account(page, provider_cfg, provider)

        server_url = provider_cfg["server_url"]
        logger.info("[%s] open server nav: %s", provider, server_url)
        page.goto(server_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(int(provider_cfg.get("form_load_wait_sec", 3) * 1000))

        expiry = read_expiry_from_page(
            page,
            timeout_sec=provider_cfg.get("expiry_load_timeout_sec", 30),
        )
        form_filled = False
        if provider_cfg.get("fill_form", True):
            _fill_renewal_form(page, screenshot_path, zhihu_url)
            form_filled = True
            if provider_cfg.get("submit_form", True):
                page.locator(CLOUD["submit_btn"]).first.click()
                page.wait_for_timeout(2000)
                logger.info("[%s] form filled and submitted", provider)
            else:
                logger.info("[%s] form filled, manual submit required", provider)
        elif provider_cfg.get("submit_form"):
            page.locator(CLOUD["submit_btn"]).first.click()
            page.wait_for_timeout(2000)
            logger.info("[%s] auto submit clicked", provider)

        pause_sec = provider_cfg.get("pause_before_close_sec", 30)
        if pause_sec > 0:
            page.wait_for_timeout(int(pause_sec * 1000))

        try:
            _do_logout(page, provider_cfg["login_url"], provider)
        except Exception as exc:
            logger.warning("[%s] logout after renewal failed: %s", provider, exc)
        session.save_state(provider_cfg["auth_state"])
        return {
            "skipped": False,
            "provider": provider,
            "login_done": True,
            "expiry_at": expiry.strftime("%Y-%m-%d %H:%M:%S"),
            "server_url": server_url,
            "page_url": page.url,
            "zhihu_url": zhihu_url,
            "screenshot_path": str(screenshot_path),
            "fill_form": form_filled,
            "submit_form": bool(provider_cfg.get("submit_form", True)),
        }
    finally:
        if session:
            session.close()
