# -*- coding: utf-8 -*-
"""Email notification helpers."""

import logging
import os
import smtplib
import traceback
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from utils.logger import DEFAULT_LOG_FILE, log_artifact_path, resolve_log_path

logger = logging.getLogger("sanfeng")

_PROVIDER_LABELS = {
    "sanfeng": "三丰云(17658501696)",
    "sanfeng2": "三丰云(18563200721)",
}

_FAILURE_LABELS = {
    "login": "知乎登录失败",
    "post": "知乎发帖失败",
}


def _resolve_email_config(config: dict[str, Any]) -> dict[str, Any] | None:
    email_cfg = (config.get("notification") or {}).get("email") or {}
    if not email_cfg.get("enabled"):
        return None

    username = os.environ.get(email_cfg.get("username_env", "SMTP_USERNAME"), "").strip()
    password = os.environ.get(email_cfg.get("password_env", "SMTP_PASSWORD"), "").strip()
    to_addr = os.environ.get(email_cfg.get("to_env", "NOTIFY_EMAIL_TO"), "").strip()
    if not to_addr:
        to_addr = str(email_cfg.get("to", "")).strip()

    if not username or not password or not to_addr:
        logger.warning("Email notification enabled but SMTP credentials/recipient missing")
        return None

    return {
        "smtp_host": email_cfg.get("smtp_host", "smtp.163.com"),
        "smtp_port": int(email_cfg.get("smtp_port", 465)),
        "use_ssl": bool(email_cfg.get("use_ssl", True)),
        "username": username,
        "password": password,
        "to": to_addr,
    }


def _send_email(
    smtp_cfg: dict[str, Any],
    *,
    subject: str,
    body: str,
    screenshot_path: str | Path | None = None,
) -> bool:
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = smtp_cfg["username"]
    msg["To"] = smtp_cfg["to"]
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if screenshot_path:
        path = Path(screenshot_path)
        if path.is_file():
            attachment = MIMEApplication(path.read_bytes(), Name=path.name)
            attachment["Content-Disposition"] = f'attachment; filename="{path.name}"'
            msg.attach(attachment)
        else:
            logger.warning("Screenshot not found for email attachment: %s", path)

    try:
        if smtp_cfg["use_ssl"]:
            with smtplib.SMTP_SSL(smtp_cfg["smtp_host"], smtp_cfg["smtp_port"], timeout=30) as server:
                server.login(smtp_cfg["username"], smtp_cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_cfg["smtp_host"], smtp_cfg["smtp_port"], timeout=30) as server:
                server.starttls()
                server.login(smtp_cfg["username"], smtp_cfg["password"])
                server.send_message(msg)
        logger.info("Notification email sent to %s: %s", smtp_cfg["to"], subject)
        return True
    except Exception as exc:
        logger.error("Failed to send notification email: %s", exc)
        return False


def send_zhihu_failure_email(
    config: dict[str, Any],
    *,
    failure_type: str,
    reason: str,
    page_url: str = "",
    page_errors: str = "",
    screenshot_path: str | Path | None = None,
    provider: str | None = None,
    article_title: str | None = None,
) -> bool:
    """Send Zhihu login/post failure notification. Returns True if sent."""
    smtp_cfg = _resolve_email_config(config)
    if not smtp_cfg:
        return False

    label = _FAILURE_LABELS.get(failure_type, "知乎操作失败")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    provider_label = _PROVIDER_LABELS.get(provider or "", provider or "")

    lines = [
        f"【{label}】需人工处理",
        "",
        f"时间：{now}",
    ]
    if provider_label:
        lines.append(f"云厂商：{provider_label}")
    if article_title:
        lines.append(f"文章标题：{article_title}")
    lines.append(f"失败原因：{reason}")
    if page_errors:
        lines.append(f"页面错误：{page_errors}")
    if page_url:
        lines.append(f"当前 URL：{page_url}")
    if screenshot_path:
        lines.append(f"截图：{screenshot_path}")
    lines.extend(
        [
            "",
            "建议操作：",
            "1. 检查知乎登录态是否正常",
            "2. 如需重新登录，运行: python scripts/init_zhihu_auth.py",
            "3. 处理完成后可用 --force --provider <name> 重跑",
        ]
    )

    return _send_email(
        smtp_cfg,
        subject=f"[云续期脚本] {label}",
        body="\n".join(lines),
        screenshot_path=screenshot_path,
    )


_RELOGIN_LABELS = {
    "pending": "知乎待扫码登录",
    "refresh": "知乎仍未登录已换新码",
    "success": "知乎登录成功",
    "timeout": "知乎扫码等待超时",
}


def send_zhihu_relogin_email(
    config: dict[str, Any],
    *,
    kind: str,
    reason: str,
    page_url: str = "",
    screenshot_path: str | Path | None = None,
) -> bool:
    """QR wait emails: pending / refresh / success / timeout."""
    smtp_cfg = _resolve_email_config(config)
    if not smtp_cfg:
        return False

    label = _RELOGIN_LABELS.get(kind, "知乎登录待处理")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"【{label}】",
        "",
        f"时间：{now}",
        f"说明：{reason}",
    ]
    if page_url:
        lines.append(f"当前 URL：{page_url}")

    if kind == "success":
        lines.extend(["", "Cookie 已写入本机 profile，后续发帖/保活会继续。"])
    else:
        lines.extend(
            [
                "",
                "请尽快用知乎 App 扫描附件二维码。",
                "这张码绑定的是服务器上正在开着的 Chrome，不要关那个窗口，也不要断远程桌面。",
                "二维码通常一两分钟就过期：过期可直接扫服务器页面上的新码，或等下一封邮件。",
                "扫码成功后页面会自动跳转，脚本会自己检测到，无需回信。",
            ]
        )

    return _send_email(
        smtp_cfg,
        subject=f"[云续期脚本] {label}",
        body="\n".join(lines),
        screenshot_path=screenshot_path if kind != "success" else None,
    )


def send_audit_stale_email(
    config: dict[str, Any],
    *,
    provider: str,
    expiry: datetime,
    hours_remaining: float,
    last_success_at: str = "",
    last_url: str = "",
) -> bool:
    """Notify that cloud expiry has not changed near deadline (possible rejected audit)."""
    smtp_cfg = _resolve_email_config(config)
    if not smtp_cfg:
        return False

    provider_label = _PROVIDER_LABELS.get(provider, provider)
    expiry_str = expiry.strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    label = f"{provider_label}到期时间未更新"

    lines = [
        f"【{label}】可能审核未通过，需人工处理",
        "",
        f"时间：{now}",
        f"云厂商：{provider_label}",
        f"当前到期时间：{expiry_str}",
        f"距离到期：{hours_remaining:.1f} 小时",
    ]
    if last_success_at:
        lines.append(f"本周期提交时间：{last_success_at}")
    if last_url:
        lines.append(f"提交的文章 URL：{last_url}")
    lines.extend(
        [
            "",
            "说明：本周期已自动提交续期，但到期时间仍未变化。",
            "可能原因：审核未通过 / 表单被驳回 / 需人工补交。",
            "",
            "建议：登录云控制台核对审核状态，必要时手动重新发帖并提交。",
        ]
    )

    return _send_email(
        smtp_cfg,
        subject=f"[云续期脚本] {label}",
        body="\n".join(lines),
    )


def send_cnblogs_failure_email(
    config: dict[str, Any],
    *,
    failure_type: str,
    reason: str,
    page_url: str = "",
    page_errors: str = "",
    screenshot_path: str | Path | None = None,
    provider: str | None = None,
    article_title: str | None = None,
) -> bool:
    """Legacy CNBlogs failure mail (kept for post_cnblogs.py)."""
    smtp_cfg = _resolve_email_config(config)
    if not smtp_cfg:
        return False

    labels = {"login": "博客园登录失败", "post": "博客园发帖失败"}
    label = labels.get(failure_type, "博客园操作失败")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    provider_label = _PROVIDER_LABELS.get(provider or "", provider or "")

    lines = [f"【{label}】需人工处理", "", f"时间：{now}"]
    if provider_label:
        lines.append(f"云厂商：{provider_label}")
    if article_title:
        lines.append(f"文章标题：{article_title}")
    lines.append(f"失败原因：{reason}")
    if page_errors:
        lines.append(f"页面错误：{page_errors}")
    if page_url:
        lines.append(f"当前 URL：{page_url}")
    if screenshot_path:
        lines.append(f"截图：{screenshot_path}")
    lines.extend(
        [
            "",
            "建议操作：",
            "1. 检查博客园登录态是否正常",
            "2. 如有验证码，手动登录后运行: python scripts/init_cnblogs_auth.py",
            "3. 处理完成后可用 --force --provider <name> 重跑",
        ]
    )
    return _send_email(
        smtp_cfg,
        subject=f"[云续期脚本] {label}",
        body="\n".join(lines),
        screenshot_path=screenshot_path,
    )


_STEP_LABELS = {
    "expiry check": "读取云到期时间",
    "keepalive": "知乎保活",
    "pipeline": "续期流水线",
    "main": "主流程",
    "AI generate": "AI 生成文章",
    "cloud renewal": "云厂商填表",
    "zhihu post": "知乎发帖",
    "zhihu login": "知乎登录",
    "browser": "启动浏览器",
}

_EXC_STEPS = {
    "ContentGenerationError": "AI generate",
    "CloudRenewalError": "cloud renewal",
    "ZhihuPostError": "zhihu post",
    "ZhihuLoginError": "zhihu login",
}


def _refine_step(exc: BaseException, step: str) -> str:
    inferred = _EXC_STEPS.get(type(exc).__name__, "")
    if inferred:
        return inferred
    if "Failed to launch browser" in str(exc) or "mkdtemp" in str(exc):
        return "browser"
    return step or "main"


def _guess_error_screenshot(exc: BaseException, provider: str | None) -> Path | None:
    text = str(exc)
    names: list[str] = []
    if "Expiry datetime not found" in text:
        names.append("expiry_not_found.png")
    if provider and ("login timeout" in text or "credentials empty" in text):
        names.append(f"{provider}_login_failed.png")
    for name in names:
        path = log_artifact_path(name)
        if path.is_file():
            return path
    return None


def notify_task_error(
    config: dict[str, Any],
    exc: BaseException,
    *,
    provider: str | None = None,
    step: str = "",
    screenshot_path: str | Path | None = None,
) -> bool:
    """Email unexpected failures. Skips Ctrl+C and errors already mailed."""
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return False
    if getattr(exc, "already_notified", False):
        logger.info("Skip duplicate error email: %s", exc)
        return False

    smtp_cfg = _resolve_email_config(config)
    if not smtp_cfg:
        try:
            exc.already_notified = True
        except Exception:
            pass
        return False

    step_key = _refine_step(exc, step)
    step_label = _STEP_LABELS.get(step_key, step_key)
    provider_label = _PROVIDER_LABELS.get(provider or "", provider or "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = (config.get("logging") or {}).get("file", DEFAULT_LOG_FILE)
    log_path = resolve_log_path(str(log_file))
    shot: Path | str | None = screenshot_path
    if shot:
        shot = Path(shot)
        if not shot.is_file():
            shot = None
    else:
        shot = _guess_error_screenshot(exc, provider)

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    if len(tb) > 2000:
        tb = tb[:2000] + "\n...(truncated)"

    lines = [
        "【任务异常】需人工处理",
        "",
        f"时间：{now}",
        f"步骤：{step_label}",
    ]
    if provider_label:
        lines.append(f"云厂商：{provider_label}")
    lines.extend(
        [
            f"异常类型：{type(exc).__name__}",
            f"失败原因：{exc}",
            f"日志：{log_path}",
        ]
    )
    if shot:
        lines.append(f"截图：{shot}")
    lines.extend(
        [
            "",
            "堆栈：",
            tb,
            "",
            "下次定时任务会再试。已单独发过知乎扫码/发帖失败的，不会再重复这封。",
        ]
    )

    sent = _send_email(
        smtp_cfg,
        subject=f"[云续期脚本] 任务异常：{step_label}",
        body="\n".join(lines),
        screenshot_path=shot,
    )
    try:
        exc.already_notified = True
    except Exception:
        pass
    return sent
