# -*- coding: utf-8 -*-
"""Expiry-based scheduling helpers."""

import re
from datetime import datetime
from pathlib import Path

from utils.logger import ROOT, load_json, save_json

EXPIRY_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")


def parse_expiry_datetime(text: str) -> datetime | None:
    match = EXPIRY_PATTERN.search(text)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")


def parse_expiry_after_label(text: str, label: str) -> datetime | None:
    """Take the datetime that follows the expiry label, not an earlier date in the same block."""
    pattern = re.compile(
        re.escape(label) + r"\s*[:\uff1a]?\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})"
    )
    match = pattern.search(text)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")


def hours_until(expiry: datetime, now: datetime | None = None) -> float:
    now = now or datetime.now()
    return (expiry - now).total_seconds() / 3600


def should_run_by_expiry(
    expiry: datetime,
    *,
    hours_before_min: float,
    hours_before_max: float,
    state_file: str,
    force: bool = False,
    ignore_cycle: bool = False,
) -> tuple[bool, str]:
    if force:
        return True, "force mode (ignore window and cycle)"

    remaining = hours_until(expiry)
    if remaining <= 0:
        return False, f"expired {abs(remaining):.1f}h ago, skip"
    if remaining > hours_before_max:
        return False, (
            f"{remaining:.1f}h until expiry, outside window "
            f"(trigger when <= {hours_before_max}h)"
        )
    if hours_before_min > 0 and remaining < hours_before_min:
        return False, (
            f"{remaining:.1f}h until expiry, below min window "
            f"[{hours_before_min}, {hours_before_max}]h"
        )

    if not ignore_cycle:
        state_path = ROOT / state_file
        state = load_json(state_path)
        expiry_key = expiry.strftime("%Y-%m-%d %H:%M:%S")
        if state.get("last_expiry_at") == expiry_key and state.get("last_success_at"):
            return False, f"expiry {expiry_key} already processed this cycle"

    suffix = "manual rerun" if ignore_cycle else "run"
    return True, f"{remaining:.1f}h until expiry, in window, {suffix}"


def mark_provider_success(
    state_file: str,
    *,
    expiry: datetime,
    zhihu_url: str,
    output_dir: Path,
) -> None:
    path = ROOT / state_file
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json(
        path,
        {
            "last_success_at": datetime.now().isoformat(timespec="seconds"),
            "last_expiry_at": expiry.strftime("%Y-%m-%d %H:%M:%S"),
            "last_url": zhihu_url,
            "last_output_dir": str(output_dir.relative_to(ROOT)),
            # Clear previous cycle's audit warning when a new submit succeeds.
            "audit_warned_for_expiry": "",
        },
    )


def should_warn_audit_stale(
    expiry: datetime,
    *,
    hours_before: float,
    state_file: str,
) -> tuple[bool, str]:
    """True when already submitted this cycle but expiry still unchanged near deadline."""
    remaining = hours_until(expiry)
    expiry_key = expiry.strftime("%Y-%m-%d %H:%M:%S")
    state = load_json(ROOT / state_file)

    if not state.get("last_success_at"):
        return False, "no prior success in state, skip audit warn"
    if state.get("last_expiry_at") != expiry_key:
        return False, (
            f"expiry changed ({state.get('last_expiry_at')} -> {expiry_key}), "
            "audit likely passed"
        )
    if remaining > hours_before:
        return False, (
            f"{remaining:.1f}h until expiry, audit warn only within "
            f"{hours_before}h"
        )
    if state.get("audit_warned_for_expiry") == expiry_key:
        return False, f"audit warn already sent for expiry {expiry_key}"

    return True, (
        f"{remaining:.1f}h until expiry, submitted but expiry unchanged, warn once"
    )


def mark_audit_warned(state_file: str, expiry: datetime) -> None:
    path = ROOT / state_file
    state = load_json(path)
    state["audit_warned_for_expiry"] = expiry.strftime("%Y-%m-%d %H:%M:%S")
    state["audit_warned_at"] = datetime.now().isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json(path, state)
