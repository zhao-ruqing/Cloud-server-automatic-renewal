# -*- coding: utf-8 -*-
"""Email notification helpers."""

import logging
import os
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

logger = logging.getLogger("sanfeng")

_FAILURE_LABELS = {
    "login": "博客园登录失败",
    "post": "博客园发帖失败",
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
    """Send failure notification email. Returns True if sent."""
    smtp_cfg = _resolve_email_config(config)
    if not smtp_cfg:
        return False

    label = _FAILURE_LABELS.get(failure_type, "博客园操作失败")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"【{label}】需人工处理",
        "",
        f"时间：{now}",
    ]
    if provider:
        lines.append(f"云厂商：{provider}")
    if article_title:
        lines.append(f"文章标题：{article_title}")
    lines.extend(
        [
            f"失败原因：{reason}",
        ]
    )
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
    body = "\n".join(lines)

    msg = MIMEMultipart()
    msg["Subject"] = f"[云续期脚本] {label}"
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
        logger.info("Failure notification email sent to %s", smtp_cfg["to"])
        return True
    except Exception as exc:
        logger.error("Failed to send notification email: %s", exc)
        return False
