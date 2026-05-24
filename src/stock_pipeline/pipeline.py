from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from stock_pipeline.config import Settings, ensure_project_dirs
from stock_pipeline.csmar_client import CsmarClient, DatasetSpec, DownloadedFile
from stock_pipeline.vpn import AccessCheck, ensure_campus_access


@dataclass(frozen=True)
class UpdateResult:
    access_check: AccessCheck
    downloaded_files: list[DownloadedFile]
    state_file: Path


def run_update(settings: Settings, auto_connect_vpn: bool = False) -> UpdateResult:
    ensure_project_dirs(settings)

    access_check = ensure_campus_access(settings, auto_connect=auto_connect_vpn)
    if not access_check.ok:
        return UpdateResult(access_check, [], _state_file(settings))

    specs = load_dataset_specs(settings.datasets_file)
    enabled_specs = [spec for spec in specs if spec.enabled]
    if not enabled_specs:
        return UpdateResult(access_check, [], _state_file(settings))

    client = CsmarClient(settings)
    state = _read_state(settings)
    today = date.today().isoformat()
    output_dir = settings.raw_data_dir / "csmar" / today

    downloaded: list[DownloadedFile] = []
    for spec in enabled_specs:
        context = {
            "name": spec.name,
            "today": today,
            "last_success_date": state.get("datasets", {})
            .get(spec.name, {})
            .get("last_success_date", state.get("last_success_date", today)),
        }
        rendered_params = _render_templates(spec.params, context)
        rendered_body = _render_templates(spec.json_body, context) if spec.json_body else None
        output_name = spec.output.format(**context)
        downloaded_file = client.download_dataset(
            spec=spec,
            rendered_params=rendered_params,
            rendered_body=rendered_body,
            output_path=output_dir / output_name,
        )
        downloaded.append(downloaded_file)
        state.setdefault("datasets", {})[spec.name] = {
            "last_success_date": today,
            "last_file": str(downloaded_file.path),
        }

    state["last_success_date"] = today
    _write_state(settings, state)

    return UpdateResult(access_check, downloaded, _state_file(settings))


def load_dataset_specs(path: Path) -> list[DatasetSpec]:
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset config not found: {path}. Run 'stock-update init' first."
        )

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    return [DatasetSpec.from_dict(item) for item in config.get("datasets", [])]


def _render_templates(value: Any, context: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**context)
    if isinstance(value, dict):
        return {key: _render_templates(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_templates(item, context) for item in value]
    return value


def _state_file(settings: Settings) -> Path:
    return settings.state_dir / "last_run.json"


def _read_state(settings: Settings) -> dict[str, Any]:
    path = _state_file(settings)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_state(settings: Settings, state: dict[str, Any]) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    with _state_file(settings).open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.write("\n")

