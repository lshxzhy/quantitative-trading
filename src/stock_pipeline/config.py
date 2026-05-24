from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    raw_data_dir: Path
    processed_data_dir: Path
    external_data_dir: Path
    state_dir: Path
    logs_dir: Path
    datasets_file: Path
    csmar_healthcheck_url: str
    csmar_api_base_url: str | None
    csmar_api_token: str | None
    vpn_connection_name: str | None
    request_timeout_seconds: int


def load_settings(
    project_root: Path | str | None = None,
    env_file: Path | str | None = None,
    load_env: bool = True,
) -> Settings:
    root = Path(project_root).resolve() if project_root else PROJECT_ROOT

    if load_env:
        load_dotenv(Path(env_file) if env_file else root / ".env")

    data_dir = _resolve_path(root, os.getenv("DATA_DIR", "data"))
    datasets_file = _resolve_path(root, os.getenv("DATASETS_FILE", "config/datasets.yml"))

    return Settings(
        project_root=root,
        data_dir=data_dir,
        raw_data_dir=data_dir / "raw",
        processed_data_dir=data_dir / "processed",
        external_data_dir=data_dir / "external",
        state_dir=root / "state",
        logs_dir=root / "logs",
        datasets_file=datasets_file,
        csmar_healthcheck_url=os.getenv("CSMAR_HEALTHCHECK_URL", "https://www.csmar.com/"),
        csmar_api_base_url=_none_if_blank(os.getenv("CSMAR_API_BASE_URL")),
        csmar_api_token=_none_if_blank(os.getenv("CSMAR_API_TOKEN")),
        vpn_connection_name=_none_if_blank(os.getenv("VPN_CONNECTION_NAME")),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
    )


def ensure_project_dirs(settings: Settings) -> None:
    for path in (
        settings.raw_data_dir,
        settings.processed_data_dir,
        settings.external_data_dir,
        settings.state_dir,
        settings.logs_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _none_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None

