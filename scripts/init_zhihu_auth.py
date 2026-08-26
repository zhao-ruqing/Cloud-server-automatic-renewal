"""初始化知乎登录态。"""

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
    print("知乎登录态初始化")
    print("=" * 55)
    print("1. 将使用系统 Chrome/Edge 打开浏览器（避免空白页）")
    print("2. 若未登录，请扫码或密码登录")
    print("3. 登录后请手动打开写文章页，确认页面可正常操作：")
    print(f"   {write_url}")
    print("4. 回到此窗口按 Enter，保存登录 Cookie")
    print("=" * 55)
    print("提示: 请用 Ctrl+C 取消，不要直接关终端窗口")
    print()

    session = None
    try:
        session = launch_auth_browser(browser_cfg, "zhihu_profile")
        page = session.page

        try:
            page.goto(write_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            print(f"\n自动打开写文章页时被跳转（可忽略）: {exc}")
            print("请在浏览器地址栏手动打开写文章页。")

        input("\n确认已在写文章页且页面正常显示后，按 Enter 保存登录态... ")

        current_url = page.url
        if "zhuanlan.zhihu.com/write" not in current_url:
            print(f"\n警告: 当前不在写文章页 ({current_url})")
            confirm = input("仍要保存当前 Cookie? [y/N]: ").strip().lower()
            if confirm != "y":
                print("已取消，未保存。")
                return

        session.save_state(zhihu_cfg["auth_state"])
        print(f"\n已保存: {zhihu_cfg['auth_state']}")
        print("可运行: python main.py --force")

    except KeyboardInterrupt:
        print("\n\n已取消（未保存）。")
    finally:
        if session:
            session.close()
            print("浏览器已关闭。")


if __name__ == "__main__":
    main()
