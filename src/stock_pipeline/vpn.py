from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass

import requests

from stock_pipeline.config import Settings


@dataclass(frozen=True)
class AccessCheck:
    ok: bool
    message: str


def check_url(url: str, timeout_seconds: int) -> AccessCheck:
    try:
        response = requests.get(url, timeout=timeout_seconds)
    except requests.RequestException as exc:
        return AccessCheck(False, f"Cannot reach {url}: {exc}")

    if response.status_code >= 500:
        return AccessCheck(False, f"{url} returned HTTP {response.status_code}")

    return AccessCheck(True, f"{url} returned HTTP {response.status_code}")


def ensure_campus_access(settings: Settings, auto_connect: bool = False) -> AccessCheck:
    first_check = check_url(settings.csmar_healthcheck_url, settings.request_timeout_seconds)
    if first_check.ok or not auto_connect:
        return first_check

    if not settings.vpn_connection_name:
        return AccessCheck(
            False,
            "Campus resource is not reachable and VPN_CONNECTION_NAME is not set in .env.",
        )

    vpn_result = connect_windows_vpn(settings.vpn_connection_name)
    if not vpn_result.ok:
        return vpn_result

    return check_url(settings.csmar_healthcheck_url, settings.request_timeout_seconds)


def connect_windows_vpn(connection_name: str) -> AccessCheck:
    if platform.system() != "Windows":
        return AccessCheck(False, "Automatic VPN connection is currently implemented for Windows only.")

    result = subprocess.run(
        ["rasdial", connection_name],
        capture_output=True,
        text=True,
        check=False,
    )

    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    if result.returncode == 0:
        return AccessCheck(True, output or f"VPN connection '{connection_name}' is connected.")

    return AccessCheck(False, output or f"rasdial failed with exit code {result.returncode}.")

