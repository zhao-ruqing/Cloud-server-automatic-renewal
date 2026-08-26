"""初始化三丰云登录态（二期预备）。"""

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
    print("三丰云登录态初始化")
    print("=" * 55)
    print("1. 将打开三丰云登录页")
    print("2. 确认账密已填充，手动点击「登录」")
    print("3. 登录成功后回到此窗口按 Enter 保存")
    print("=" * 55)

    session = None
    try:
        session = launch_auth_browser(browser_cfg, "sanfeng_profile")
        page = session.page
        page.goto(sanfeng_cfg["login_url"], wait_until="domcontentloaded", timeout=60000)

        input("\n登录成功后按 Enter 保存登录态... ")
        session.save_state(sanfeng_cfg["auth_state"])
        print(f"已保存: {sanfeng_cfg['auth_state']}")

    except KeyboardInterrupt:
        print("\n已取消（未保存）。")
    finally:
        if session:
            session.close()


if __name__ == "__main__":
    main()
