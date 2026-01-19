from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


APP_NAME = "anderaa_reader"
CONFIG_FILE_NAME = "sensor_config.json"
STATE_FILE_NAME = "app_state.json"


def get_user_config_dir() -> Path:
    """Return per-user config directory.

    Windows: %APPDATA%\\anderaa_reader
    Others:  ~/.config/anderaa_reader
    """
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def get_user_config_path() -> Path:
    return get_user_config_dir() / CONFIG_FILE_NAME


def get_user_state_path() -> Path:
    return get_user_config_dir() / STATE_FILE_NAME


def resolve_config_path(repo_local_path: Path) -> Path:
    """Prefer user config if it exists; otherwise use repo-local path."""
    user_path = get_user_config_path()
    if user_path.exists():
        return user_path
    return repo_local_path


def load_config(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"sensors": []}


def save_config(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def load_sensors(repo_local_path: Path) -> List[Dict[str, Any]]:
    """Load sensors list from resolved config path."""
    resolved = resolve_config_path(repo_local_path)
    config = load_config(resolved)
    sensors = config.get("sensors", [])
    return sensors if isinstance(sensors, list) else []


def save_sensors_to_user_config(sensors: List[Dict[str, Any]]) -> Path:
    """Save sensor configs to per-user config file and return the path used."""
    path = get_user_config_path()
    save_config(path, {"sensors": sensors})
    return path


def load_state() -> Dict[str, Any]:
    """Load small persistent app state (UI/settings) from per-user config dir."""
    path = get_user_state_path()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        # Don't brick the app if state is corrupted.
        return {}


def save_state(payload: Dict[str, Any]) -> Path:
    """Save small persistent app state (UI/settings) to per-user config dir."""
    path = get_user_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)
    return path
