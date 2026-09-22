from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .registry import Registry
from .util import atomic_write_json

MANAGED_PREFIX = "owntone-announce:"


def _managed_accessory(name: str, item: dict[str, Any], hb: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": MANAGED_PREFIX + name,
        "name": item.get("label") or name,
        "type": "Switch",
        "protocol": "HomeKit",
        "defaultState": "off",
        "commandOn": f"{hb['command']} play {name}",
        "autoReset": {
            "type": "TIMEOUT",
            "time": int(hb["auto_reset_ms"]),
            "units": "MILLISECONDS",
        },
    }


def reconcile_homebridge(data: dict[str, Any], registry: Registry, hb: dict[str, Any]) -> dict[str, Any]:
    platforms = data.setdefault("platforms", [])
    alias = hb["dummy_platform"]
    platform = next((p for p in platforms if p.get("platform") == alias), None)
    if platform is None:
        raise RuntimeError(
            f"Homebridge Dummy platform '{alias}' not found. Install/configure homebridge-dummy first."
        )

    accessories = platform.setdefault("accessories", [])
    unmanaged = [
        a for a in accessories if not str(a.get("id", "")).startswith(MANAGED_PREFIX)
    ]
    managed = [
        _managed_accessory(name, item, hb)
        for name, item in sorted(registry.messages.items())
        if item.get("homebridge")
    ]
    platform["accessories"] = unmanaged + managed
    return data


def sync_homebridge(registry: Registry, cfg: dict[str, Any], *, restart: bool | None = None) -> int:
    hb = cfg["homebridge"]
    config_value = hb.get("config_path")
    if not config_value:
        raise RuntimeError("homebridge.config_path is not configured")
    path = Path(config_value)
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    reconcile_homebridge(data, registry, hb)

    backup = path.with_suffix(path.suffix + ".owntone-announce.bak")
    shutil.copy2(path, backup)
    atomic_write_json(path, data)

    do_restart = hb.get("restart_on_sync", False) if restart is None else restart
    if do_restart:
        command = hb.get("restart_command")
        if not isinstance(command, list) or not command:
            raise RuntimeError("homebridge.restart_command must be a non-empty JSON array")
        subprocess.run([str(x) for x in command], check=True)
    return sum(1 for item in registry.messages.values() if item.get("homebridge"))
