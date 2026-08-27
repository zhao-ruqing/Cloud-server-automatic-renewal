# -*- coding: utf-8 -*-
"""Shared cloud renewal: login, read expiry, fill renewal form."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.browser import BrowserSession, launch_browser
from utils.expiry_scheduler import parse_expiry_after_label, parse_expiry_datetime
from utils.selectors import CLOUD

logger = logging.getLogger("sanfeng")


class CloudRenewalError(Exception):
    pass


def _is_login_page(page: Page) -> bool:
    if "/login" in page.url.lower():
        return True
    login_btn = page.locator(CLOUD["login_btn"])
    return login_btn.count() > 0 and login_btn.first.is_visible()


def _do_login(page: Page, wait_sec: float, provider: str) -> None:
    login_btn = page.locator(CLOUD["login_btn"])
    login_btn.wait_for(state="visible", timeout=15000)

    username = page.locator(CLOUD["username"])
    password = page.locator(CLOUD["password"])
    if username.input_value().strip() == "" or password.input_value().strip() == "":
        raise CloudRenewalError(
            f"{provider} credentials empty. Run init script first."
        )

    login_btn.click()
    page.wait_for_timeout(int(wait_sec * 1000))
    try:
        page.wait_for_function(
            "() => !window.location.href.toLowerCase().includes('/login')",
            timeout=30000,
        )
    except PlaywrightTimeoutError as exc:
        page.screenshot(path=f"logs/{provider}_login_failed.png", full_page=False)
        raise CloudRenewalError(f"{provider} login timeout") from exc


def read_expiry_from_page(page: Page) -> datetime:
    label = CLOUD["expiry_label"]

    # Prefer datetime immediately after the "expiry" label (not "created at").
    body_text = page.locator("body").inner_text()
    expiry = parse_expiry_after_label(body_text, label)
    if expiry:
        logger.info("Parsed expiry after label: %s", expiry.strftime("%Y-%m-%d %H:%M:%S"))
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
                    logger.info(
                        "Parsed expiry from next column: %s",
                        expiry.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    return expiry
        except Exception:
            continue

    page.screenshot(path="logs/expiry_not_found.png", full_page=False)
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
        page.goto(provider_cfg["login_url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        if _is_login_page(page):
            _do_login(page, provider_cfg.get("login_wait_sec", 2), provider)

        server_url = provider_cfg["server_url"]
        page.goto(server_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(int(provider_cfg.get("form_load_wait_sec", 3) * 1000))
        expiry = read_expiry_from_page(page)
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

        logger.info("[%s] open login: %s", provider, provider_cfg["login_url"])
        page.goto(provider_cfg["login_url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        if _is_login_page(page):
            _do_login(page, provider_cfg.get("login_wait_sec", 2), provider)

        server_url = provider_cfg["server_url"]
        logger.info("[%s] open server nav: %s", provider, server_url)
        page.goto(server_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(int(provider_cfg.get("form_load_wait_sec", 3) * 1000))

        expiry = read_expiry_from_page(page)
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
