# -*- coding: utf-8 -*-
import os
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

ROOT = Path(__file__).resolve().parent.parent

# Common Windows Chrome install paths
DEFAULT_CHROME_PATHS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe",
]


def resolve_chrome_executable(browser_cfg: dict[str, Any]) -> Path | None:
    """Resolve local Google Chrome path (avoid Chrome for Testing)."""
    configured = browser_cfg.get("executable_path")
    if configured:
        path = Path(configured)
        if path.exists():
            return path

    for path in DEFAULT_CHROME_PATHS:
        if path.exists():
            return path
    return None


def _ensure_playwright_temp() -> Path:
    """Windows RDP often sets TEMP to ...\\Temp\\<sessionId>, which may not exist.

    Playwright then fails with: ENOENT mkdtemp '...\\playwright-artifacts-XXXXXX'
    """
    candidates: list[Path] = []
    for key in ("TEMP", "TMP", "TMPDIR"):
        value = os.environ.get(key)
        if value:
            candidates.append(Path(value))
    candidates.append(Path(tempfile.gettempdir()))
    candidates.append(ROOT / ".tmp" / "playwright")

    seen: set[str] = set()
    for path in candidates:
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".pw_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError:
            continue
        os.environ["TEMP"] = resolved
        os.environ["TMP"] = resolved
        os.environ["TMPDIR"] = resolved
        return path

    raise RuntimeError(
        "Cannot create a writable TEMP directory for Playwright. "
        "Create the folder shown in the error, or set TEMP to an existing path."
    )


def _start_playwright() -> Playwright:
    _ensure_playwright_temp()
    return sync_playwright().start()


def _format_launch_error(exc: Exception) -> str:
    text = str(exc)
    if "mkdtemp" in text or "playwright-artifacts" in text:
        return (
            "Playwright temp directory is missing (common on Windows Remote Desktop). "
            f"Original error: {text}"
        )
    return (
        "Failed to launch browser. Install Google Chrome "
        f"or set browser.executable_path. Error: {text}"
    )


def _build_launch_kwargs(browser_cfg: dict[str, Any], *, for_persistent: bool) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "headless": browser_cfg.get("headless", False),
        "args": browser_cfg.get("args", ["--disable-blink-features=AutomationControlled"]),
        "ignore_https_errors": True,
    }
    if not for_persistent:
        kwargs["slow_mo"] = browser_cfg.get("slow_mo", 0)

    chrome_path = resolve_chrome_executable(browser_cfg)
    if chrome_path:
        kwargs["executable_path"] = str(chrome_path)
        return kwargs

    # Fallback to Edge if Chrome is missing
    channel = browser_cfg.get("channel")
    if channel and channel != "chrome":
        kwargs["channel"] = channel
    else:
        kwargs["channel"] = "msedge"
    return kwargs


class BrowserSession:
    """Playwright browser session wrapper."""

    def __init__(
        self,
        playwright: Playwright,
        browser: Browser | None,
        context: BrowserContext,
        page: Page,
        *,
        persistent: bool = False,
        browser_label: str = "",
    ):
        self.playwright = playwright
        self.browser = browser
        self.context = context
        self.page = page
        self.persistent = persistent
        self.browser_label = browser_label

    def close(self) -> None:
        try:
            self.context.close()
        except Exception:
            pass
        if self.browser is not None:
            try:
                self.browser.close()
            except Exception:
                pass
        try:
            self.playwright.stop()
        except Exception:
            pass

    def save_state(self, path: str | Path) -> None:
        state_path = ROOT / path if not Path(path).is_absolute() else Path(path)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        self.context.storage_state(path=str(state_path))


def launch_auth_browser(browser_cfg: dict[str, Any], profile_subdir: str) -> BrowserSession:
    """Init script: persistent profile + system Chrome."""
    playwright = _start_playwright()
    profile_dir = ROOT / "auth" / profile_subdir
    profile_dir.mkdir(parents=True, exist_ok=True)

    kwargs = _build_launch_kwargs(browser_cfg, for_persistent=True)
    kwargs["viewport"] = browser_cfg.get("viewport", {"width": 1280, "height": 900})

    chrome_path = kwargs.get("executable_path")
    label = f"Google Chrome ({chrome_path})" if chrome_path else f"Edge channel"

    try:
        context = playwright.chromium.launch_persistent_context(str(profile_dir), **kwargs)
    except Exception as exc:
        playwright.stop()
        raise RuntimeError(_format_launch_error(exc)) from exc

    page = context.pages[0] if context.pages else context.new_page()
    print(f"Browser started ({label})")
    return BrowserSession(
        playwright, None, context, page, persistent=True, browser_label=label
    )


def launch_browser(
    browser_cfg: dict[str, Any],
    auth_state: str | Path | None = None,
    profile_subdir: str | None = None,
) -> BrowserSession:
    """Launch browser. Use persistent profile when profile_subdir is set."""
    playwright = _start_playwright()
    kwargs = _build_launch_kwargs(browser_cfg, for_persistent=bool(profile_subdir))

    if profile_subdir:
        profile_dir = ROOT / "auth" / profile_subdir
        profile_dir.mkdir(parents=True, exist_ok=True)
        kwargs["viewport"] = browser_cfg.get("viewport", {"width": 1280, "height": 900})

        try:
            context = playwright.chromium.launch_persistent_context(str(profile_dir), **kwargs)
        except Exception as exc:
            playwright.stop()
            raise RuntimeError(_format_launch_error(exc)) from exc

        page = context.pages[0] if context.pages else context.new_page()
        chrome_path = kwargs.get("executable_path", "")
        label = f"Google Chrome ({chrome_path})" if chrome_path else "Edge"
        return BrowserSession(
            playwright, None, context, page, persistent=True, browser_label=label
        )

    try:
        browser = playwright.chromium.launch(**kwargs)
    except Exception as exc:
        playwright.stop()
        raise RuntimeError(_format_launch_error(exc)) from exc

    context_kwargs: dict[str, Any] = {
        "viewport": browser_cfg.get("viewport", {"width": 1280, "height": 900}),
        "ignore_https_errors": True,
    }
    if auth_state:
        state_path = ROOT / auth_state if not Path(auth_state).is_absolute() else Path(auth_state)
        if state_path.exists():
            context_kwargs["storage_state"] = str(state_path)

    context = browser.new_context(**context_kwargs)
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page = context.new_page()
    return BrowserSession(playwright, browser, context, page)
