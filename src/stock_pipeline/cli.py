from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from stock_pipeline.config import PROJECT_ROOT, load_settings
from stock_pipeline.pipeline import run_update
from stock_pipeline.vpn import ensure_campus_access


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stock-update")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create local .env and config/datasets.yml if missing.")

    login_parser = subparsers.add_parser("login-webvpn", help="Open WebVPN and save manual login state.")
    login_parser.add_argument("--headless", action="store_true", help="Run browser without a visible window.")

    csmar_parser = subparsers.add_parser("open-csmar", help="Open WebVPN with saved login state for CSMAR.")
    csmar_parser.add_argument("--headless", action="store_true", help="Run browser without a visible window.")

    check_parser = subparsers.add_parser("check-vpn", help="Check CSMAR/campus access.")
    check_parser.add_argument("--connect-vpn", action="store_true", help="Try Windows rasdial first if access fails.")

    update_parser = subparsers.add_parser("update", help="Run one CSMAR data update.")
    update_parser.add_argument("--connect-vpn", action="store_true", help="Try Windows rasdial first if access fails.")

    args = parser.parse_args(argv)

    if args.command == "init":
        return _init_project()

    settings = load_settings()

    if args.command == "login-webvpn":
        from stock_pipeline.browser_crawler import login_webvpn

        result = login_webvpn(settings, headless=args.headless)
        print(f"Saved login state: {result.storage_state}")
        print(f"Saved screenshot: {result.screenshot}")
        return 0

    if args.command == "open-csmar":
        from stock_pipeline.browser_crawler import open_csmar_session

        result = open_csmar_session(settings, headless=args.headless)
        print(f"Saved login state: {result.storage_state}")
        print(f"Saved screenshot: {result.screenshot}")
        print(f"Downloads directory: {result.downloads_dir}")
        return 0

    if args.command == "check-vpn":
        result = ensure_campus_access(settings, auto_connect=args.connect_vpn)
        print(result.message)
        return 0 if result.ok else 1

    if args.command == "update":
        result = run_update(settings, auto_connect_vpn=args.connect_vpn)
        print(result.access_check.message)
        if not result.access_check.ok:
            return 1
        if not result.downloaded_files:
            print("No enabled datasets were downloaded. Edit config/datasets.yml after you have CSMAR API details.")
            return 0
        for item in result.downloaded_files:
            print(f"Downloaded {item.dataset_name}: {item.path} ({item.bytes_written} bytes)")
        print(f"State saved to {result.state_file}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _init_project() -> int:
    copies = [
        (PROJECT_ROOT / ".env.example", PROJECT_ROOT / ".env"),
        (PROJECT_ROOT / "config" / "datasets.example.yml", PROJECT_ROOT / "config" / "datasets.yml"),
    ]

    for source, target in copies:
        if target.exists():
            print(f"Exists: {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        print(f"Created: {target}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

