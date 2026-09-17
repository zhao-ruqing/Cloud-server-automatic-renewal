# -*- coding: utf-8 -*-
"""Standalone Zhihu keepalive (also called from main.py when idle)."""

import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from steps.zhihu_keepalive import run_zhihu_keepalive, should_run_keepalive
from utils.logger import DEFAULT_LOG_FILE, setup_logger
from utils.run_lock import RunLock


def main() -> None:
    load_dotenv(ROOT / ".env")
    with (ROOT / "config.yaml").open(encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger = setup_logger(config.get("logging", {}).get("file", DEFAULT_LOG_FILE))

    lock = RunLock()
    acquired, lock_reason = lock.acquire()
    logger.info("run lock: %s", lock_reason)
    if not acquired:
        return

    try:
        ok, reason = should_run_keepalive(config)
        logger.info("keepalive check: %s", reason)
        if ok:
            run_zhihu_keepalive(config)
        else:
            logger.info("skip keepalive")
    finally:
        lock.release()


if __name__ == "__main__":
    main()
