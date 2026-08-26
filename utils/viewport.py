import random
from typing import Any


def random_viewport(browser_cfg: dict[str, Any]) -> dict[str, int]:
    """在基准视口附近随机偏移，避免每次截图尺寸完全一致。"""
    base = browser_cfg.get("viewport", {"width": 1280, "height": 900})
    jitter = browser_cfg.get("viewport_jitter", {"width": 80, "height": 60})
    minimum = browser_cfg.get("viewport_min", {"width": 1180, "height": 820})

    width = base["width"] + random.randint(-jitter["width"], jitter["width"])
    height = base["height"] + random.randint(-jitter["height"], jitter["height"])

    return {
        "width": max(minimum["width"], width),
        "height": max(minimum["height"], height),
    }
