# -*- coding: utf-8 -*-
"""Main entry: expiry-based scheduling + Zhihu post + cloud renewal."""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from steps.cloud_renewal import fetch_cloud_expiry, submit_cloud_renewal
from steps.generate_content import generate_content
from steps.post_zhihu import post_zhihu
from steps.zhihu_keepalive import run_zhihu_keepalive, should_run_keepalive
from utils.expiry_scheduler import mark_provider_success, should_run_by_expiry
from utils.logger import create_output_dir, save_json, setup_logger
from utils.scheduler import write_meta

CLOUD_PROVIDERS = ("sanfeng", "abeiyun")


def load_config(path: Path | None = None) -> dict:
    with (path or ROOT / "config.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_providers_to_run(config: dict, force: bool, logger) -> list[str]:
    to_run: list[str] = []
    browser_cfg = config["browser"]

    for name in CLOUD_PROVIDERS:
        cfg = config.get(name, {})
        if not cfg.get("enabled"):
            logger.info("[%s] disabled", name)
            continue

        if force:
            logger.info("[%s] force mode, will run", name)
            to_run.append(name)
            continue

        try:
            expiry = fetch_cloud_expiry(cfg, browser_cfg, name)
            ok, reason = should_run_by_expiry(
                expiry,
                hours_before_min=cfg.get("run_hours_before_min", 20),
                hours_before_max=cfg.get("run_hours_before_max", 22),
                state_file=cfg.get("state_file", f"data/{name}_schedule.json"),
            )
            logger.info("[%s] expiry=%s | %s", name, expiry.strftime("%Y-%m-%d %H:%M:%S"), reason)
            if ok:
                to_run.append(name)
        except Exception as exc:
            logger.error("[%s] expiry check failed: %s", name, exc)

    return to_run


def main(force: bool = False, keepalive_only: bool = False) -> int:
    load_dotenv(ROOT / ".env")
    config = load_config()
    logger = setup_logger(config.get("logging", {}).get("file", "logs/run.log"))

    if keepalive_only:
        ok, reason = should_run_keepalive(config)
        logger.info("keepalive-only: %s", reason)
        if ok:
            run_zhihu_keepalive(config)
        return 0

    providers = resolve_providers_to_run(config, force, logger)

    if not providers:
        ok, reason = should_run_keepalive(config)
        logger.info("No cloud renewal due. keepalive: %s", reason)
        if ok:
            run_zhihu_keepalive(config)
        return 0

    output_dir = create_output_dir(config.get("output", {}).get("base_dir", "output"))
    logger.info("Providers to run: %s | output: %s", providers, output_dir)
    started = time.time()
    content: dict | None = None
    result: dict | None = None

    try:
        logger.info("Step 1: AI generate")
        content = generate_content(config)
        save_json(
            output_dir / "content.json",
            {**content, "topics": config["zhihu"]["topics"], "created_at": datetime.now().isoformat(timespec="seconds")},
        )

        logger.info("Step 2: Zhihu post")
        result = post_zhihu(content["title"], content["body"], config, output_dir)
        save_json(
            output_dir / "content.json",
            {
                **content,
                "topics": config["zhihu"]["topics"],
                "url": result["url"],
                "screenshot_path": result["screenshot_path"],
                "screenshot_viewport": result.get("screenshot_viewport"),
                "review_hint": result.get("review_hint", ""),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        logger.info("Article URL: %s", result["url"])

        for idx, provider in enumerate(providers, start=3):
            logger.info("Step %s: %s renewal", idx, provider)
            cloud_result = submit_cloud_renewal(
                provider, result["screenshot_path"], result["url"], config
            )
            save_json(output_dir / f"{provider}.json", cloud_result)

            expiry_str = cloud_result.get("expiry_at")
            if expiry_str:
                expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
                cfg = config[provider]
                mark_provider_success(
                    cfg.get("state_file", f"data/{provider}_schedule.json"),
                    expiry=expiry,
                    zhihu_url=result["url"],
                    output_dir=output_dir,
                )

        duration = time.time() - started
        write_meta(output_dir, success=True, duration_sec=duration)
        logger.info("Done in %.1fs", duration)
        return 0

    except Exception as exc:
        duration = time.time() - started
        write_meta(output_dir, success=False, duration_sec=duration, error=str(exc))
        logger.error("Failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Run all enabled providers now")
    parser.add_argument("--keepalive-only", action="store_true", help="Only refresh Zhihu session")
    args = parser.parse_args()
    raise SystemExit(main(force=args.force, keepalive_only=args.keepalive_only))
