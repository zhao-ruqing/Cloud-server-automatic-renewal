# -*- coding: utf-8 -*-
"""Zhihu publish flow."""

import time
from pathlib import Path
from typing import Any

import pyperclip
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.browser import BrowserSession, launch_browser
from utils.selectors import ZHIHU
from utils.viewport import random_viewport


class ZhihuPostError(Exception):
    pass


def _is_login_required(page) -> bool:
    url = page.url
    if "signin" in url or "login" in url:
        return True
    if page.locator(f'text="{ZHIHU["login_text"]}"').count() > 0:
        return True
    if page.locator(".SignFlowModal").count() > 0:
        return True
    return False


def _fill_title(page, title: str) -> None:
    locator = page.locator(ZHIHU["title_input"])
    locator.wait_for(state="visible", timeout=15000)
    locator.click()
    locator.fill(title)
    page.wait_for_timeout(500)


def _fill_body(page, body: str) -> None:
    editor = page.locator(ZHIHU["body_editor"])
    editor.wait_for(state="visible", timeout=15000)
    editor.click()
    pyperclip.copy(body)
    page.keyboard.press("Control+A")
    page.keyboard.press("Control+V")
    page.wait_for_timeout(800)


def _add_topic(page, topic: str) -> None:
    add_btn = page.locator(ZHIHU["add_topic_btn"])
    if add_btn.count() > 0 and add_btn.first.is_visible():
        add_btn.first.click()
        page.wait_for_timeout(300)

    search = page.locator(ZHIHU["topic_search"])
    search.wait_for(state="visible", timeout=10000)
    search.click()
    search.fill("")
    search.fill(topic)
    page.wait_for_timeout(1200)

    item = page.get_by_text(topic, exact=True).first
    try:
        item.wait_for(state="visible", timeout=8000)
        item.click()
    except PlaywrightTimeoutError as exc:
        page.screenshot(path="logs/topic_not_found.png", full_page=True)
        raise ZhihuPostError(f"topic not found: {topic}") from exc
    page.wait_for_timeout(500)


def _click_publish(page, timeout_sec: int, *, before_delay_sec: float, after_delay_sec: float) -> str:
    publish = page.locator(ZHIHU["publish_btn"])
    publish.wait_for(state="visible", timeout=15000)

    deadline = time.time() + 30
    while time.time() < deadline:
        if publish.is_enabled():
            break
        page.wait_for_timeout(500)
    else:
        raise ZhihuPostError("publish button stayed disabled")

    page.wait_for_timeout(int(before_delay_sec * 1000))
    publish.click()
    page.wait_for_timeout(int(after_delay_sec * 1000))

    try:
        page.wait_for_url("**/zhuanlan.zhihu.com/p/**", timeout=timeout_sec * 1000)
    except PlaywrightTimeoutError as exc:
        html_path = Path("logs/publish_timeout.html")
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(page.content(), encoding="utf-8")
        page.screenshot(path="logs/publish_timeout.png", full_page=True)
        raise ZhihuPostError(f"publish timeout ({timeout_sec}s)") from exc

    return _to_article_url(page.url)


def _to_article_url(url: str) -> str:
    cleaned = url.split("?")[0].split("#")[0].rstrip("/")
    if cleaned.endswith("/edit"):
        cleaned = cleaned[: -len("/edit")]
    return cleaned


def _open_article_and_screenshot(
    page,
    article_url: str,
    screenshot_path: Path,
    browser_cfg: dict[str, Any],
) -> tuple[str, dict[str, int]]:
    page.goto(article_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    final_url = _to_article_url(page.url)
    if page.url.rstrip("/").endswith("/edit") or "/edit" in page.url:
        page.goto(final_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        final_url = _to_article_url(page.url)

    try:
        page.locator("h1.Post-Title, .Post-Header h1, article h1").first.wait_for(
            state="visible", timeout=20000
        )
    except PlaywrightTimeoutError:
        if page.locator(ZHIHU["title_input"]).count() > 0:
            raise ZhihuPostError(f"still on editor page: {page.url}")

    viewport = random_viewport(browser_cfg)
    page.set_viewport_size(viewport)
    page.wait_for_timeout(1000)
    page.screenshot(path=str(screenshot_path), full_page=False)
    return final_url, viewport


def post_zhihu(
    title: str,
    body: str,
    config: dict[str, Any],
    output_dir: Path,
    topics: list[str] | None = None,
    screenshot_name: str = "article.png",
) -> dict[str, str]:
    zhihu_cfg = config["zhihu"]
    browser_cfg = config["browser"]
    topic_list = topics if topics is not None else []
    session: BrowserSession | None = None

    try:
        session = launch_browser(
            browser_cfg,
            auth_state=zhihu_cfg["auth_state"],
            profile_subdir=zhihu_cfg.get("profile_dir", "zhihu_profile"),
        )
        page = session.page
        page.goto(zhihu_cfg["write_url"], wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        if _is_login_required(page):
            raise ZhihuPostError("Zhihu login expired. Run: python scripts/init_zhihu_auth.py")

        _fill_title(page, title)
        _fill_body(page, body)

        for topic in topic_list:
            _add_topic(page, topic)

        article_url = _click_publish(
            page,
            zhihu_cfg["publish_timeout_sec"],
            before_delay_sec=zhihu_cfg.get("before_publish_delay_sec", 2),
            after_delay_sec=zhihu_cfg.get("after_publish_delay_sec", 3),
        )
        screenshot_path = output_dir / screenshot_name
        final_url, screenshot_viewport = _open_article_and_screenshot(
            page, article_url, screenshot_path, browser_cfg
        )

        review_hint = ""
        if page.locator(f'text="{ZHIHU["review_text"]}"').count() > 0:
            review_hint = "reviewing"

        return {
            "url": final_url,
            "screenshot_path": str(screenshot_path),
            "screenshot_viewport": screenshot_viewport,
            "review_hint": review_hint,
        }
    finally:
        if session:
            session.save_state(zhihu_cfg["auth_state"])
            session.close()
