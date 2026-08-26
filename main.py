"""三丰云自动续期 — 主入口（一期：AI + 知乎发帖）。"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from steps.generate_content import generate_content
from steps.post_zhihu import post_zhihu
from steps.submit_sanfeng import submit_sanfeng
from utils.logger import create_output_dir, save_json, setup_logger
from utils.scheduler import mark_success, should_run, write_meta


def load_config(path: Path | None = None) -> dict:
    cfg_path = path or ROOT / "config.yaml"
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def main(force: bool = False) -> int:
    load_dotenv(ROOT / ".env")
    config = load_config()
    logger = setup_logger(config.get("logging", {}).get("file", "logs/run.log"))

    schedule = config["schedule"]
    if not force:
        ok, reason = should_run(schedule["interval_days"], schedule["state_file"])
        logger.info(reason)
        if not ok:
            return 0

    output_dir = create_output_dir(config.get("output", {}).get("base_dir", "output"))
    logger.info("输出目录: %s", output_dir)
    started = time.time()
    content: dict | None = None
    result: dict | None = None

    try:
        logger.info("步骤 1/3: AI 生成内容")
        content = generate_content(config)
        save_json(
            output_dir / "content.json",
            {
                **content,
                "topics": config["zhihu"]["topics"],
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        logger.info("标题: %s", content["title"])

        logger.info("步骤 2/3: 知乎发帖")
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
        logger.info("文章 URL: %s", result["url"])
        if result.get("screenshot_viewport"):
            vp = result["screenshot_viewport"]
            logger.info("截图视口: %sx%s", vp["width"], vp["height"])

        if config.get("sanfeng", {}).get("enabled"):
            logger.info("步骤 3/3: 三丰云登录并打开续期页")
            sanfeng_result = submit_sanfeng(result["screenshot_path"], result["url"], config)
            save_json(output_dir / "sanfeng.json", sanfeng_result)
            logger.info("三丰云续期页: %s", sanfeng_result.get("form_url", ""))
        else:
            logger.info("步骤 3/3: 三丰云已跳过（sanfeng.enabled=false）")

        duration = time.time() - started
        write_meta(output_dir, success=True, duration_sec=duration)
        mark_success(schedule["state_file"], result["url"], output_dir)
        logger.info("流程成功，耗时 %.1fs", duration)
        return 0

    except Exception as exc:
        duration = time.time() - started
        write_meta(output_dir, success=False, duration_sec=duration, error=str(exc))
        if content:
            save_json(
                output_dir / "content.json",
                {
                    **content,
                    "topics": config["zhihu"]["topics"],
                    "url": result.get("url") if result else "",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        logger.error("失败: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="三丰云自动续期脚本")
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略 5 天间隔限制，立即执行",
    )
    args = parser.parse_args()
    raise SystemExit(main(force=args.force))
