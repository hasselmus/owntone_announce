from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class OwnToneHTTP:
    def __init__(self, host: str, port: int):
        self.base = f"http://{host}:{int(port)}/api"

    def _json(self, path: str) -> Any:
        with urllib.request.urlopen(self.base + path, timeout=3) as r:
            return json.load(r)

    def _put(self, path: str, body: bytes | None = None) -> None:
        req = urllib.request.Request(self.base + path, data=body, method="PUT")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=3):
            pass

    def config(self) -> dict[str, Any]:
        return self._json("/config")

    def player(self) -> dict[str, Any]:
        return self._json("/player")

    def outputs(self) -> list[dict[str, Any]]:
        return self._json("/outputs").get("outputs", [])

    def set_output_volume(self, output_id: str, volume: int) -> None:
        query = urllib.parse.urlencode({"volume": int(volume), "output_id": str(output_id)})
        self._put(f"/player/volume?{query}")

    def rescan(self) -> None:
        self._put("/update")


def virtual_file_path(path: Path) -> str:
    return "file:" + str(path.resolve())
