# -*- coding: utf-8 -*-
"""Init Zhihu login state."""

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

    zhihu_cfg = config["zhihu"]
    write_url = zhihu_cfg["write_url"]
    browser_cfg = {**config["browser"], "headless": False, "slow_mo": 0}

    print("=" * 55)
    print("Zhihu login init")
    print("=" * 55)
    print("1. Chrome/Edge will open")
    print("2. Login if needed")
    print("3. Open write page and confirm it works:")
    print(f"   {write_url}")
    print("4. Back here, press Enter to save cookies")
    print("=" * 55)
    print("Cancel with Ctrl+C")
    print()

    session = None
    try:
        session = launch_auth_browser(browser_cfg, "zhihu_profile")
        page = session.page

        try:
            page.goto(write_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            print(f"\nAuto navigation interrupted (ok): {exc}")
            print("Open the write page in the address bar.")

        input("\nAfter write page is OK, press Enter to save... ")

        current_url = page.url
        if "zhuanlan.zhihu.com/write" not in current_url:
            print(f"\nWarning: not on write page ({current_url})")
            confirm = input("Save cookies anyway? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Cancelled.")
                return

        session.save_state(zhihu_cfg["auth_state"])
        print(f"\nSaved: {zhihu_cfg['auth_state']}")
        print("Run: python main.py --force")

    except KeyboardInterrupt:
        print("\n\nCancelled.")
    finally:
        if session:
            session.close()
            print("Browser closed.")


if __name__ == "__main__":
    main()
