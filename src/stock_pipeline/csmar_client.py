from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from stock_pipeline.config import Settings


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    enabled: bool
    method: str
    endpoint: str
    params: dict[str, Any] = field(default_factory=dict)
    json_body: dict[str, Any] | None = None
    output: str = "{name}_{today}.csv"
    description: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DatasetSpec":
        return cls(
            name=str(value["name"]),
            enabled=bool(value.get("enabled", False)),
            method=str(value.get("method", "GET")).upper(),
            endpoint=str(value["endpoint"]),
            params=dict(value.get("params", {})),
            json_body=value.get("json_body"),
            output=str(value.get("output", "{name}_{today}.csv")),
            description=value.get("description"),
        )


@dataclass(frozen=True)
class DownloadedFile:
    dataset_name: str
    path: Path
    bytes_written: int


class CsmarClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.csmar_api_base_url:
            raise ValueError("CSMAR_API_BASE_URL is not set. Fill .env after obtaining official API docs.")

        self.settings = settings
        self.session = requests.Session()

        if settings.csmar_api_token:
            self.session.headers.update({"Authorization": f"Bearer {settings.csmar_api_token}"})

    def download_dataset(
        self,
        spec: DatasetSpec,
        rendered_params: dict[str, Any],
        rendered_body: dict[str, Any] | None,
        output_path: Path,
    ) -> DownloadedFile:
        url = urljoin(self.settings.csmar_api_base_url.rstrip("/") + "/", spec.endpoint.lstrip("/"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if spec.method == "GET":
            response = self.session.get(
                url,
                params=rendered_params,
                timeout=self.settings.request_timeout_seconds,
            )
        elif spec.method == "POST":
            response = self.session.post(
                url,
                params=rendered_params,
                json=rendered_body,
                timeout=self.settings.request_timeout_seconds,
            )
        else:
            raise ValueError(f"Unsupported method for {spec.name}: {spec.method}")

        response.raise_for_status()
        output_path.write_bytes(response.content)

        return DownloadedFile(
            dataset_name=spec.name,
            path=output_path,
            bytes_written=len(response.content),
        )

