from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

from stock_pipeline.config import Settings


@dataclass(frozen=True)
class BrowserRunResult:
    storage_state: Path
    screenshot: Path
    downloads_dir: Path


def login_webvpn(settings: Settings, headless: bool = False) -> BrowserRunResult:
    """Open SWUFE WebVPN and save login state after the user logs in manually."""
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir = settings.data_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir = _daily_downloads_dir(settings)
    downloads_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True)
        _register_context_download_saver(context, downloads_dir)
        page = context.new_page()

        page.goto(settings.webvpn_url, wait_until="domcontentloaded")
        print(f"Opened WebVPN: {settings.webvpn_url}")
        print("Log in manually in the browser window. Do not type your password in this terminal.")
        input("After WebVPN login succeeds, press Enter here to save the browser login state...")

        screenshot = screenshot_dir / "webvpn_after_login.png"
        page.screenshot(path=screenshot, full_page=True)
        context.storage_state(path=settings.webvpn_storage_state)
        browser.close()

    return BrowserRunResult(
        storage_state=settings.webvpn_storage_state,
        screenshot=screenshot,
        downloads_dir=downloads_dir,
    )


def open_csmar_session(settings: Settings, headless: bool = False) -> BrowserRunResult:
    """Open WebVPN with saved login state so the user can navigate to CSMAR."""
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir = settings.data_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir = _daily_downloads_dir(settings)
    downloads_dir.mkdir(parents=True, exist_ok=True)

    if not settings.webvpn_storage_state.exists():
        raise FileNotFoundError(
            f"WebVPN login state not found: {settings.webvpn_storage_state}. "
            "Run 'stock-update login-webvpn' first."
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(
            accept_downloads=True,
            storage_state=settings.webvpn_storage_state,
        )
        _register_context_download_saver(context, downloads_dir)
        page = context.new_page()

        page.goto(settings.webvpn_url, wait_until="domcontentloaded")
        print(f"Opened WebVPN with saved login state: {settings.webvpn_url}")
        print("Use the browser window to open CSMAR through the WebVPN portal.")
        print(f"Downloaded files will be saved to: {downloads_dir}")
        input("When you finish this CSMAR session, press Enter here to close the browser...")

        screenshot = screenshot_dir / "csmar_session_end.png"
        page.screenshot(path=screenshot, full_page=True)
        context.storage_state(path=settings.webvpn_storage_state)
        browser.close()

    return BrowserRunResult(
        storage_state=settings.webvpn_storage_state,
        screenshot=screenshot,
        downloads_dir=downloads_dir,
    )


def _daily_downloads_dir(settings: Settings) -> Path:
    return settings.raw_data_dir / "csmar" / date.today().isoformat()


def _register_context_download_saver(context: BrowserContext, downloads_dir: Path) -> None:
    def register_page(page: Page) -> None:
        _register_download_saver(page, downloads_dir)

    context.on("page", register_page)


def _register_download_saver(page: Page, downloads_dir: Path) -> None:
    def save_download(download) -> None:
        suggested_name = download.suggested_filename
        target = _unique_path(downloads_dir / suggested_name)
        download.save_as(target)
        print(f"Saved download: {target}")

    page.on("download", save_download)


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    for index in range(1, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate

    raise FileExistsError(f"Too many files with the same name near: {path}")
