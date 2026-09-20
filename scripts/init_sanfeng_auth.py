# -*- coding: utf-8 -*-
"""Init Sanfeng login state for one of the two accounts."""

import argparse
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from steps.cloud_renewal import login_cloud_account
from utils.browser import launch_auth_browser


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        choices=("sanfeng", "sanfeng2"),
        default="sanfeng",
        help="Which Sanfeng account to login",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    with (ROOT / "config.yaml").open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    provider_cfg = config[args.provider]
    browser_cfg = {**config["browser"], "headless": False, "slow_mo": 0}

    print("=" * 55)
    print(f"Sanfeng login init ({args.provider})")
    print("=" * 55)
    print("1. Login page will open")
    print("2. Script fills credentials and logs in")
    print("3. Press Enter here to save")
    print("=" * 55)

    session = None
    try:
        session = launch_auth_browser(
            browser_cfg, provider_cfg.get("profile_dir", "sanfeng_profile")
        )
        login_cloud_account(session.page, provider_cfg, args.provider)

        input("\nAfter login, press Enter to save... ")
        session.save_state(provider_cfg["auth_state"])
        print(f"Saved: {provider_cfg['auth_state']}")

    except KeyboardInterrupt:
        print("\nCancelled.")
    finally:
        if session:
            session.close()


if __name__ == "__main__":
    main()
