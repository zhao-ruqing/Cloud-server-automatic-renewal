"""三丰云登录与续期页（表单提交为二期）。"""

import logging
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.browser import BrowserSession, launch_browser
from utils.selectors import SANFENG

logger = logging.getLogger("sanfeng")


class SanfengSubmitError(Exception):
    pass


def _is_login_page(page) -> bool:
    url = page.url.lower()
    if "/login" in url:
        return True
    login_btn = page.locator(SANFENG["login_btn"])
    return login_btn.count() > 0 and login_btn.first.is_visible()


def _do_login(page, wait_sec: float) -> None:
    login_btn = page.locator(SANFENG["login_btn"])
    login_btn.wait_for(state="visible", timeout=15000)

    username = page.locator(SANFENG["username"])
    password = page.locator(SANFENG["password"])
    if username.input_value().strip() == "" or password.input_value().strip() == "":
        raise SanfengSubmitError(
            "三丰云账密未自动填充。请先运行: python scripts/init_sanfeng_auth.py"
        )

    login_btn.click()
    page.wait_for_timeout(int(wait_sec * 1000))

    try:
        page.wait_for_function(
            "() => !window.location.href.toLowerCase().includes('/login')",
            timeout=30000,
        )
    except PlaywrightTimeoutError as exc:
        page.screenshot(path="logs/sanfeng_login_failed.png", full_page=False)
        raise SanfengSubmitError(
            "三丰云登录超时，可能账密错误或页面变更。已保存 logs/sanfeng_login_failed.png"
        ) from exc


def submit_sanfeng(screenshot_path: str | Path, zhihu_url: str, config: dict[str, Any]) -> dict[str, Any]:
    sanfeng_cfg = config.get("sanfeng", {})
    if not sanfeng_cfg.get("enabled"):
        return {"skipped": True}

    browser_cfg = config["browser"]
    session: BrowserSession | None = None

    try:
        session = launch_browser(
            browser_cfg,
            auth_state=sanfeng_cfg.get("auth_state"),
            profile_subdir=sanfeng_cfg.get("profile_dir", "sanfeng_profile"),
        )
        page = session.page

        logger.info("打开三丰云登录页: %s", sanfeng_cfg["login_url"])
        page.goto(sanfeng_cfg["login_url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        if _is_login_page(page):
            logger.info("检测到登录页，点击登录")
            _do_login(page, sanfeng_cfg.get("login_wait_sec", 2))
        else:
            logger.info("已在登录态，跳过登录按钮")

        form_url = sanfeng_cfg["form_url"]
        logger.info("打开续期页: %s", form_url)
        page.goto(form_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(int(sanfeng_cfg.get("form_load_wait_sec", 3) * 1000))

        if sanfeng_cfg.get("submit_form"):
            raise SanfengSubmitError("续期表单提交为二期功能，当前仅登录并打开续期页")

        pause_sec = sanfeng_cfg.get("pause_before_close_sec", 5)
        if pause_sec > 0:
            logger.info("停留 %.1fs 便于查看页面", pause_sec)
            page.wait_for_timeout(int(pause_sec * 1000))

        session.save_state(sanfeng_cfg["auth_state"])

        return {
            "skipped": False,
            "login_done": True,
            "form_url": page.url,
            "zhihu_url": zhihu_url,
            "screenshot_path": str(screenshot_path),
            "submit_form": False,
        }
    finally:
        if session:
            session.close()
