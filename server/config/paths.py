from __future__ import annotations

import shutil
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def storage_root() -> Path:
    path = repo_root() / "storage"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_root() -> Path:
    path = storage_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def live_data_root() -> Path:
    path = data_root() / "live"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backups_root() -> Path:
    path = storage_root() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def media_root() -> Path:
    path = storage_root() / "media"
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_db_path() -> Path:
    return repo_root() / "server" / "db" / "app.db"


def app_db_path() -> Path:
    return live_data_root() / "stock-penaek.db"


def ensure_local_data_layout() -> Path:
    db_path = app_db_path()
    if db_path.exists() and db_path.stat().st_size > 0:
        return db_path

    legacy = legacy_db_path()
    if legacy.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, db_path)
    return db_path
