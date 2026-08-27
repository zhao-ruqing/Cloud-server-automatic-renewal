# -*- coding: utf-8 -*-
"""Zhihu session keepalive."""

import logging
from datetime import datetime
from typing import Any

from utils.browser import BrowserSession, launch_browser
from utils.logger import ROOT, load_json, save_json
from utils.selectors import ZHIHU

logger = logging.getLogger("sanfeng")


def should_run_keepalive(config: dict[str, Any]) -> tuple[bool, str]:
    zhihu_cfg = config.get("zhihu", {})
    if not zhihu_cfg.get("keepalive_enabled", True):
        return False, "keepalive disabled"

    interval = zhihu_cfg.get("keepalive_interval_hours", 2)
    state_file = zhihu_cfg.get("keepalive_state_file", "data/zhihu_keepalive.json")
    state = load_json(ROOT / state_file)
    last = state.get("last_keepalive_at")
    if not last:
        return True, "no keepalive history"

    last_dt = datetime.fromisoformat(last)
    hours = (datetime.now() - last_dt).total_seconds() / 3600
    if hours >= interval:
        return True, f"last keepalive {hours:.1f}h ago (>={interval}h)"
    return False, f"last keepalive {hours:.1f}h ago (<{interval}h)"


def run_zhihu_keepalive(config: dict[str, Any]) -> dict[str, Any]:
    zhihu_cfg = config["zhihu"]
    browser_cfg = config["browser"]
    state_file = zhihu_cfg.get("keepalive_state_file", "data/zhihu_keepalive.json")

    session: BrowserSession | None = None
    try:
        session = launch_browser(
            browser_cfg,
            auth_state=zhihu_cfg.get("auth_state"),
            profile_subdir=zhihu_cfg.get("profile_dir", "zhihu_profile"),
        )
        page = session.page
        urls = [
            zhihu_cfg.get("write_url", "https://zhuanlan.zhihu.com/write"),
            "https://www.zhihu.com/",
        ]
        for url in urls:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

        login_required = (
            "signin" in page.url
            or page.locator(f'text="{ZHIHU["login_text"]}"').count() > 0
        )
        session.save_state(zhihu_cfg["auth_state"])

        result = {
            "ok": not login_required,
            "login_required": login_required,
            "last_url": page.url,
            "last_keepalive_at": datetime.now().isoformat(timespec="seconds"),
        }
        save_json(ROOT / state_file, result)
        if login_required:
            logger.warning("Zhihu keepalive: login expired, run init_zhihu_auth.py")
        else:
            logger.info("Zhihu keepalive ok: %s", page.url)
        return result
    finally:
        if session:
            session.close()
