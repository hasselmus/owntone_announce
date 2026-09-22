from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .util import atomic_write_json, default_label, validate_name


class Registry:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "messages": {}}
        with self.path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("messages"), dict):
            raise ValueError(f"Invalid registry: {self.path}")
        return data

    @property
    def messages(self) -> dict[str, dict[str, Any]]:
        return self.data["messages"]

    def get(self, name: str) -> dict[str, Any] | None:
        return self.messages.get(name)

    def put(
        self,
        name: str,
        *,
        text: str,
        voice: str,
        filename: str,
        label: str | None = None,
        homebridge: bool | None = None,
    ) -> dict[str, Any]:
        validate_name(name)
        existing = self.messages.get(name, {})
        item = {
            "text": text,
            "voice": voice,
            "file": filename,
            "label": label if label is not None else existing.get("label", default_label(name)),
            "homebridge": (
                bool(homebridge)
                if homebridge is not None
                else bool(existing.get("homebridge", False))
            ),
        }
        self.messages[name] = item
        return item

    def remove(self, name: str) -> dict[str, Any] | None:
        validate_name(name)
        return self.messages.pop(name, None)

    def save(self) -> None:
        atomic_write_json(self.path, self.data)
