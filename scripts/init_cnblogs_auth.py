# -*- coding: utf-8 -*-
"""Init CNBlogs login state (username/password saved in profile)."""

import getpass
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.browser import launch_auth_browser
from utils.selectors import CNBLOGS


def main() -> None:
    load_dotenv(ROOT / ".env")
    with (ROOT / "config.yaml").open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    cnblogs_cfg = config["cnblogs"]
    browser_cfg = {**config["browser"], "headless": False, "slow_mo": 0}

    username = os.environ.get(cnblogs_cfg.get("username_env", "CNBLOGS_USERNAME"), "").strip()
    password = os.environ.get(cnblogs_cfg.get("password_env", "CNBLOGS_PASSWORD"), "").strip()

    print("=" * 55)
    print("CNBlogs login init")
    print("=" * 55)
    print("1. Login page will open")
    if username:
        print(f"2. Username from env: {username}")
    else:
        username = input("CNBlogs username: ").strip()
    if not password:
        password = getpass.getpass("CNBlogs password: ")
    print("3. Credentials will be filled (password visible in browser field)")
    print("4. Click Login, solve captcha if needed")
    print("5. Press Enter here to save")
    print("=" * 55)

    session = None
    try:
        session = launch_auth_browser(browser_cfg, cnblogs_cfg.get("profile_dir", "cnblogs_profile"))
        page = session.page
        page.goto(cnblogs_cfg["login_url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        user_input = page.locator(CNBLOGS["username"])
        pass_input = page.locator(CNBLOGS["password"])
        user_input.wait_for(state="visible", timeout=15000)
        if user_input.input_value().strip() == "" and username:
            user_input.fill(username)
        if pass_input.input_value().strip() == "" and password:
            pass_input.fill(password)

        input("\nAfter login, press Enter to save... ")
        session.save_state(cnblogs_cfg["auth_state"])
        print(f"Saved: {cnblogs_cfg['auth_state']}")

    except KeyboardInterrupt:
        print("\nCancelled.")
    finally:
        if session:
            session.close()


if __name__ == "__main__":
    main()
