# -*- coding: utf-8 -*-
from typing import Any

from steps.cloud_renewal import submit_cloud_renewal


def submit_sanfeng(screenshot_path, zhihu_url, config: dict[str, Any]) -> dict[str, Any]:
    return submit_cloud_renewal("sanfeng", screenshot_path, zhihu_url, config)


def submit_abeiyun(screenshot_path, zhihu_url, config: dict[str, Any]) -> dict[str, Any]:
    return submit_cloud_renewal("abeiyun", screenshot_path, zhihu_url, config)
