from pathlib import Path

from stock_pipeline.config import load_settings


def test_load_settings_resolves_relative_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", "my-data")
    monkeypatch.setenv("DATASETS_FILE", "my-config/datasets.yml")

    settings = load_settings(project_root=tmp_path, load_env=False)

    assert settings.data_dir == tmp_path / "my-data"
    assert settings.datasets_file == tmp_path / "my-config" / "datasets.yml"
    assert settings.raw_data_dir == tmp_path / "my-data" / "raw"


def test_load_settings_accepts_absolute_dataset_file(tmp_path, monkeypatch):
    dataset_file = tmp_path / "datasets.yml"
    monkeypatch.setenv("DATASETS_FILE", str(dataset_file))

    settings = load_settings(project_root=Path("C:/example"), load_env=False)

    assert settings.datasets_file == dataset_file

