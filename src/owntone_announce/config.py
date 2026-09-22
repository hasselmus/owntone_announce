from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("/etc/owntone-announce/config.json")

DEFAULT_CONFIG: dict[str, Any] = {
    "owntone": {
        "host": "127.0.0.1",
        "http_port": 3689,
        "mpd_port": 6600,
        "audio_dir": "/var/owntone/announcements",
    },
    "playback": {
        "minimum_volume": 40,
        "trailing_silence_seconds": 2.0,
        "restore_margin_seconds": 1.0,
        "timeout_seconds": 30,
    },
    "tts": {
        "voice": "en-GB-SoniaNeural",
    },
    "state_dir": "/var/lib/owntone-announce",
    "homebridge": {
        "config_path": None,
        "dummy_platform": "HomebridgeDummy",
        "command": "/usr/local/bin/owntone-announce",
        "auto_reset_ms": 500,
        "restart_on_sync": False,
        "restart_command": ["hb-service", "restart"],
    },
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def config_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("OWNTONE_ANNOUNCE_CONFIG")
    return Path(env) if env else DEFAULT_CONFIG_PATH


def load_config(explicit: str | None = None) -> dict[str, Any]:
    path = config_path(explicit)
    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    with path.open("r", encoding="utf-8") as f:
        user = json.load(f)
    if not isinstance(user, dict):
        raise ValueError(f"Configuration root must be an object: {path}")
    return _merge(DEFAULT_CONFIG, user)


def state_dir(cfg: dict[str, Any]) -> Path:
    return Path(cfg["state_dir"])


def registry_path(cfg: dict[str, Any]) -> Path:
    return state_dir(cfg) / "messages.json"
