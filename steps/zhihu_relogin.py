# -*- coding: utf-8 -*-
"""Keep Zhihu login page open, email QR, poll until logged in."""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.browser import BrowserSession
from utils.logger import ROOT, log_artifact_path, save_json
from utils.notify import send_zhihu_relogin_email
from utils.selectors import ZHIHU

logger = logging.getLogger("sanfeng")

DEFAULT_LOGIN_URL = "https://www.zhihu.com/signin?next=%2F"
_SCAN_PENDING_MARKERS = ("请在手机上确认", "扫描成功", "已扫描")
_QR_EXPIRED_MARKERS = ("已过期", "二维码失效", "点击刷新")
_STATUS_REASONS = {
    "logged_in": "已离开登录页",
    "scan_pending": "已扫码，请在手机上确认登录（本轮不刷新页面）",
    "captcha": "页面出现验证码，需人工处理",
    "qr_expired": "二维码已过期，已刷新新码",
    "waiting_scan": "仍在登录页等待扫码",
    "unknown": "仍在登录页，未能识别二维码区域",
}


def is_zhihu_login_required(page) -> bool:
    url = page.url
    if "signin" in url or "login" in url:
        return True
    if page.locator(f'text="{ZHIHU["login_text"]}"').count() > 0:
        return True
    if page.locator(".SignFlowModal").count() > 0:
        return True
    return False


def diagnose_zhihu_login_page(page) -> str:
    if not is_zhihu_login_required(page):
        return "logged_in"
    try:
        body = page.locator("body").inner_text(timeout=2000)
    except Exception:
        body = ""
    if any(marker in body for marker in _SCAN_PENDING_MARKERS):
        return "scan_pending"
    if page.locator(ZHIHU["captcha"]).count() > 0:
        return "captcha"
    if any(marker in body for marker in _QR_EXPIRED_MARKERS):
        return "qr_expired"
    if page.locator(f'{ZHIHU["qr_container"]}, {ZHIHU["qr_image"]}').count() > 0:
        return "waiting_scan"
    return "unknown"


def _reason_text(status: str) -> str:
    return _STATUS_REASONS.get(status, status)


def _capture_login_screenshot(page) -> Path:
    path = log_artifact_path(
        f"zhihu_login_qr_{datetime.now().strftime('%H%M%S')}.png"
    )
    qr = page.locator(ZHIHU["qr_container"])
    try:
        if qr.count() > 0 and qr.first.is_visible():
            qr.first.screenshot(path=str(path))
            return path
    except Exception as exc:
        logger.warning("QR container screenshot failed, fallback to page: %s", exc)
    page.screenshot(path=str(path), full_page=False)
    return path


def _open_login_page(page, login_url: str) -> None:
    page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)
    try:
        page.locator(ZHIHU["qr_container"]).first.wait_for(
            state="visible", timeout=15000
        )
    except Exception:
        logger.warning("QR container not visible yet: %s", page.url)


def _write_relogin_state(state_file: str, payload: dict[str, Any]) -> None:
    save_json(ROOT / state_file, payload)


def _emit_relogin_email(config: dict[str, Any], **kwargs) -> bool:
    sent = send_zhihu_relogin_email(config, **kwargs)
    shot = kwargs.get("screenshot_path")
    if sent:
        logger.info("Zhihu relogin email sent (%s)", kwargs.get("kind"))
    else:
        logger.warning(
            "Zhihu relogin email NOT sent (%s). Scan the open Chrome window, "
            "or open screenshot: %s",
            kwargs.get("kind"),
            shot or "(none)",
        )
    return sent


def _mark_logged_in(
    session: BrowserSession,
    config: dict[str, Any],
    zhihu_cfg: dict[str, Any],
    state_file: str,
    started_at: str,
    page_url: str,
    log_msg: str,
) -> None:
    session.save_state(zhihu_cfg.get("auth_state", "auth/zhihu_state.json"))
    _emit_relogin_email(config, kind="success", reason="扫码登录成功", page_url=page_url)
    _write_relogin_state(
        state_file,
        {
            "status": "ok",
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    logger.info(log_msg)


def wait_for_zhihu_login(session: BrowserSession, config: dict[str, Any]) -> bool:
    """Keep the current browser on the login page until scan succeeds or timeout.

    Returns True if logged in. Caller keeps owning the session.
    """
    zhihu_cfg = config.get("zhihu") or {}
    login_url = zhihu_cfg.get("login_url", DEFAULT_LOGIN_URL)
    poll_sec = float(zhihu_cfg.get("relogin_poll_sec", 20))
    email_interval_sec = float(zhihu_cfg.get("relogin_email_interval_minutes", 10)) * 60
    max_hours = float(zhihu_cfg.get("relogin_wait_max_hours", 12))
    state_file = zhihu_cfg.get("relogin_state_file", "data/zhihu_relogin.json")
    page = session.page

    started = time.monotonic()
    deadline = started + max(max_hours, 0.05) * 3600
    started_at = datetime.now().isoformat(timespec="seconds")
    _write_relogin_state(
        state_file,
        {
            "status": "waiting",
            "started_at": started_at,
            "reason": "login required",
        },
    )

    _open_login_page(page, login_url)
    status = diagnose_zhihu_login_page(page)
    if status == "logged_in":
        _mark_logged_in(
            session,
            config,
            zhihu_cfg,
            state_file,
            started_at,
            page.url,
            "Zhihu already logged in after opening login URL",
        )
        return True

    shot = _capture_login_screenshot(page)
    _emit_relogin_email(
        config,
        kind="pending",
        reason=_reason_text(status),
        page_url=page.url,
        screenshot_path=shot,
    )
    last_email_at = time.monotonic()
    last_heartbeat_at = 0.0
    logger.info(
        "Zhihu QR wait started (%s). Keep Chrome open and scan the QR. "
        "Screenshot: %s | timeout %.1fh",
        status,
        shot,
        max_hours,
    )

    while time.monotonic() < deadline:
        try:
            page.wait_for_timeout(int(max(poll_sec, 1) * 1000))
            status = diagnose_zhihu_login_page(page)
            now = time.monotonic()
            if now - last_heartbeat_at >= 120:
                remain_min = max(deadline - now, 0) / 60
                logger.info(
                    "still waiting for Zhihu scan (%s), %.0f min left, Chrome must stay open",
                    status,
                    remain_min,
                )
                last_heartbeat_at = now
        except Exception as exc:
            logger.error("Zhihu QR wait interrupted: %s", exc)
            _emit_relogin_email(
                config,
                kind="timeout",
                reason=f"等待过程中浏览器或页面异常：{exc}",
                page_url="",
            )
            _write_relogin_state(
                state_file,
                {
                    "status": "timeout",
                    "started_at": started_at,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                    "reason": str(exc),
                },
            )
            return False
        if status == "logged_in":
            _mark_logged_in(
                session,
                config,
                zhihu_cfg,
                state_file,
                started_at,
                page.url,
                f"Zhihu QR wait succeeded: {page.url}",
            )
            return True

        if time.monotonic() - last_email_at < email_interval_sec:
            if status == "qr_expired":
                logger.info("Zhihu QR expired on live page, refreshing without email")
                _open_login_page(page, login_url)
            continue

        refresh_reason = _reason_text(status)
        if status != "scan_pending":
            _open_login_page(page, login_url)
            status = diagnose_zhihu_login_page(page)
            if status == "logged_in":
                _mark_logged_in(
                    session,
                    config,
                    zhihu_cfg,
                    state_file,
                    started_at,
                    page.url,
                    "Zhihu logged in during QR refresh",
                )
                return True
            if status == "qr_expired":
                refresh_reason = _reason_text("qr_expired")
            else:
                refresh_reason = _reason_text(status)
        else:
            refresh_reason = _reason_text("scan_pending")

        shot = _capture_login_screenshot(page)
        _emit_relogin_email(
            config,
            kind="refresh",
            reason=refresh_reason,
            page_url=page.url,
            screenshot_path=shot,
        )
        last_email_at = time.monotonic()
        _write_relogin_state(
            state_file,
            {
                "status": "waiting",
                "started_at": started_at,
                "last_email_at": datetime.now().isoformat(timespec="seconds"),
                "reason": refresh_reason,
            },
        )

    timeout_reason = (
        f"已达等待上限 {max_hours:g} 小时，浏览器将关闭；下次定时任务会再开一轮"
    )
    shot = _capture_login_screenshot(page)
    _emit_relogin_email(
        config,
        kind="timeout",
        reason=timeout_reason,
        page_url=page.url,
        screenshot_path=shot,
    )
    _write_relogin_state(
        state_file,
        {
            "status": "timeout",
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "reason": timeout_reason,
        },
    )
    logger.warning("Zhihu QR wait timed out after %.1fh", max_hours)
    return False
