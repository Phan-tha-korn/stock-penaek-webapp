from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_repo_path(value: str | Path | None, fallback_relative: str | Path | None = None) -> Path:
    raw = str(value or "").strip()
    candidates: list[Path] = []

    def add_candidate(path: Path | None) -> None:
        if path is None:
            return
        if path not in candidates:
            candidates.append(path)

    if raw:
        native = Path(raw).expanduser()
        if native.is_absolute():
            add_candidate(native)

        windows = PureWindowsPath(raw)
        if windows.is_absolute() or "\\" in raw:
            win_parts = [
                part
                for part in windows.parts
                if part not in {windows.anchor, "\\", "/"} and not part.endswith(":")
            ]
            if len(win_parts) >= 2:
                add_candidate(repo_root() / Path(*win_parts[-2:]))
            if windows.name:
                add_candidate(repo_root() / "credentials" / windows.name)
                add_candidate(repo_root() / windows.name)

        if not native.is_absolute():
            add_candidate(repo_root() / Path(raw.replace("\\", "/")))

    if fallback_relative:
        add_candidate(repo_root() / Path(fallback_relative))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else Path()


def load_master_config() -> dict[str, Any]:
    path = repo_root() / "config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_master_config(cfg: dict[str, Any]) -> None:
    path = repo_root() / "config.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

