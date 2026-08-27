# -*- coding: utf-8 -*-
"""Init Sanfeng login state."""

import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.browser import launch_auth_browser


def main() -> None:
    load_dotenv(ROOT / ".env")
    with (ROOT / "config.yaml").open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    sanfeng_cfg = config["sanfeng"]
    browser_cfg = {**config["browser"], "headless": False, "slow_mo": 0}

    print("=" * 55)
    print("Sanfeng login init")
    print("=" * 55)
    print("1. Login page will open")
    print("2. Confirm credentials filled, click Login")
    print("3. Press Enter here to save")
    print("=" * 55)

    session = None
    try:
        session = launch_auth_browser(browser_cfg, "sanfeng_profile")
        page = session.page
        page.goto(sanfeng_cfg["login_url"], wait_until="domcontentloaded", timeout=60000)

        input("\nAfter login, press Enter to save... ")
        session.save_state(sanfeng_cfg["auth_state"])
        print(f"Saved: {sanfeng_cfg['auth_state']}")

    except KeyboardInterrupt:
        print("\nCancelled.")
    finally:
        if session:
            session.close()


if __name__ == "__main__":
    main()
