# -*- coding: utf-8 -*-
"""Abeiyun login and renewal form fill (manual submit)."""

import logging
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.browser import BrowserSession, launch_browser
from utils.selectors import ABEIYUN

logger = logging.getLogger("sanfeng")


class AbeiyunSubmitError(Exception):
    pass


def _is_login_page(page) -> bool:
    url = page.url.lower()
    if "/login" in url:
        return True
    login_btn = page.locator(ABEIYUN["login_btn"])
    return login_btn.count() > 0 and login_btn.first.is_visible()


def _do_login(page, wait_sec: float) -> None:
    login_btn = page.locator(ABEIYUN["login_btn"])
    login_btn.wait_for(state="visible", timeout=15000)

    username = page.locator(ABEIYUN["username"])
    password = page.locator(ABEIYUN["password"])
    if username.input_value().strip() == "" or password.input_value().strip() == "":
        raise AbeiyunSubmitError(
            "Abeiyun credentials empty. Run: python scripts/init_abeiyun_auth.py"
        )

    login_btn.click()
    page.wait_for_timeout(int(wait_sec * 1000))

    try:
        page.wait_for_function(
            "() => !window.location.href.toLowerCase().includes('/login')",
            timeout=30000,
        )
    except PlaywrightTimeoutError as exc:
        page.screenshot(path="logs/abeiyun_login_failed.png", full_page=False)
        raise AbeiyunSubmitError(
            "Abeiyun login timeout. See logs/abeiyun_login_failed.png"
        ) from exc


def _open_renewal_form(page) -> None:
    url_input = page.locator(ABEIYUN["url_input"])
    if url_input.count() > 0 and url_input.first.is_visible():
        logger.info("Renewal form already visible")
        return

    nav_btn = page.locator(ABEIYUN["nav_extend_btn"]).first
    try:
        nav_btn.wait_for(state="visible", timeout=15000)
        nav_btn.click()
        logger.info("Clicked nav 'free extend' button")
        page.wait_for_timeout(1500)
    except PlaywrightTimeoutError:
        logger.warning("Nav button not found, trying tab")

    url_input = page.locator(ABEIYUN["url_input"])
    if url_input.count() > 0 and url_input.first.is_visible():
        return

    tab = page.locator(ABEIYUN["extend_tab"])
    if tab.count() > 0 and tab.first.is_visible():
        tab.first.click()
        page.wait_for_timeout(1000)

    try:
        url_input.first.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeoutError as exc:
        page.screenshot(path="logs/abeiyun_form_not_found.png", full_page=False)
        raise AbeiyunSubmitError(
            "Renewal form not found. See logs/abeiyun_form_not_found.png"
        ) from exc


def _fill_renewal_form(page, screenshot_path: Path, zhihu_url: str) -> None:
    _open_renewal_form(page)

    url_input = page.locator(ABEIYUN["url_input"]).first
    url_input.click()
    url_input.fill("")
    url_input.fill(zhihu_url)
    page.wait_for_timeout(500)

    file_input = page.locator(ABEIYUN["file_input"])
    if file_input.count() == 0:
        raise AbeiyunSubmitError("File input #fileImg1 not found")
    file_input.set_input_files(str(screenshot_path))
    page.wait_for_timeout(1500)
    logger.info("URL filled and screenshot uploaded; waiting for manual submit")


def submit_abeiyun(
    screenshot_path: str | Path,
    zhihu_url: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    abei_cfg = config.get("abeiyun", {})
    if not abei_cfg.get("enabled"):
        return {"skipped": True}

    screenshot_path = Path(screenshot_path)
    if not screenshot_path.exists():
        raise AbeiyunSubmitError(f"Screenshot not found: {screenshot_path}")

    browser_cfg = config["browser"]
    session: BrowserSession | None = None

    try:
        session = launch_browser(
            browser_cfg,
            auth_state=abei_cfg.get("auth_state"),
            profile_subdir=abei_cfg.get("profile_dir", "abeiyun_profile"),
        )
        page = session.page

        logger.info("Open Abeiyun login: %s", abei_cfg["login_url"])
        page.goto(abei_cfg["login_url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        if _is_login_page(page):
            logger.info("Login page detected, clicking login")
            _do_login(page, abei_cfg.get("login_wait_sec", 2))
        else:
            logger.info("Already logged in")

        server_url = abei_cfg["server_url"]
        logger.info("Open server nav page: %s", server_url)
        page.goto(server_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(int(abei_cfg.get("form_load_wait_sec", 3) * 1000))

        form_filled = False
        if abei_cfg.get("fill_form", True):
            _fill_renewal_form(page, screenshot_path, zhihu_url)
            form_filled = True

        if abei_cfg.get("submit_form"):
            submit = page.locator(ABEIYUN["submit_btn"]).first
            submit.click()
            logger.info("Auto submit clicked (submit_form=true)")
        else:
            logger.info("Manual submit required")

        pause_sec = abei_cfg.get("pause_before_close_sec", 30)
        if pause_sec > 0:
            logger.info("Pause %.1fs for manual submit", pause_sec)
            page.wait_for_timeout(int(pause_sec * 1000))

        session.save_state(abei_cfg["auth_state"])

        return {
            "skipped": False,
            "login_done": True,
            "server_url": server_url,
            "page_url": page.url,
            "zhihu_url": zhihu_url,
            "screenshot_path": str(screenshot_path),
            "fill_form": form_filled,
            "submit_form": False,
        }
    finally:
        if session:
            session.close()
