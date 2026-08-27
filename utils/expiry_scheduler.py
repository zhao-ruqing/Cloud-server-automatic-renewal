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
    if remaining < 0:
        return False, f"expired {abs(remaining):.1f}h ago, skip"
    if not (hours_before_min <= remaining <= hours_before_max):
        return False, (
            f"{remaining:.1f}h until expiry, outside window "
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
        },
    )
