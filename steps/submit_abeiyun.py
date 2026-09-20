# -*- coding: utf-8 -*-
"""Compatibility wrapper: Abeiyun is replaced by the second Sanfeng account."""
from typing import Any

from steps.cloud_renewal import submit_cloud_renewal


def submit_abeiyun(screenshot_path, zhihu_url, config: dict[str, Any]) -> dict[str, Any]:
    return submit_cloud_renewal("sanfeng2", screenshot_path, zhihu_url, config)
