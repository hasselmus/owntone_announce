from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .homebridge import sync_homebridge
from .mpd import MPDClient, MPDError, quote
from .owntone import virtual_file_path
from .registry import Registry
from .tts import synthesize_wav
from .util import validate_name


class AnnouncementService:
    def __init__(self, cfg: dict[str, Any], registry: Registry):
        self.cfg = cfg
        self.registry = registry
        ow = cfg["owntone"]
        self.audio_dir = Path(ow["audio_dir"])
        self.mpd = MPDClient(ow["host"], int(ow["mpd_port"]))

    def _wait_indexed(self, wav: Path, timeout: float = 60.0) -> None:
        wanted = virtual_file_path(wav)
        virtual_dir = "file:" + str(wav.parent.resolve())
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                lines = self.mpd.command(f"listallinfo {quote(virtual_dir)}")
                found = {line[6:] for line in lines if line.startswith("file: ")}
                if wanted in found:
                    return
            except (MPDError, OSError):
                pass
            time.sleep(0.5)
        raise TimeoutError(f"OwnTone did not index {wav} within {timeout:.0f}s")

    def _index_marker(self, wav: Path) -> tuple[str | None, str | None] | None:
        wanted = virtual_file_path(wav)
        virtual_dir = "file:" + str(wav.parent.resolve())
        lines = self.mpd.command(f"listallinfo {quote(virtual_dir)}")

        current: str | None = None
        modified: str | None = None
        duration: str | None = None
        for line in lines:
            if line.startswith("file: "):
                if current == wanted:
                    return modified, duration
                current = line[6:]
                modified = None
                duration = None
            elif current == wanted:
                if line.startswith("Last-Modified: "):
                    modified = line[len("Last-Modified: "):]
                elif line.startswith("duration: "):
                    duration = line[len("duration: "):]

        if current == wanted:
            return modified, duration
        return None

    def _wait_reindexed(
        self,
        wav: Path,
        previous: tuple[str | None, str | None] | None,
        timeout: float = 60.0,
    ) -> None:
        if previous is None:
            self._wait_indexed(wav, timeout)
            return

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                marker = self._index_marker(wav)
                if marker is not None and marker != previous:
                    return
            except (MPDError, OSError):
                pass
            time.sleep(0.25)
        raise TimeoutError(f"OwnTone did not re-index {wav} within {timeout:.0f}s")

    def add(
        self,
        name: str,
        text: str,
        *,
        voice: str | None = None,
        label: str | None = None,
        homebridge: bool | None = None,
    ) -> dict[str, Any]:
        validate_name(name)
        if not text.strip():
            raise ValueError("Announcement text cannot be empty")
        existing = self.registry.get(name) or {}
        was_homebridge = bool(existing.get("homebridge", False))
        selected_voice = voice or existing.get("voice") or self.cfg["tts"]["voice"]
        filename = f"{name}.wav"
        destination = self.audio_dir / filename
        synthesize_wav(
            text,
            selected_voice,
            destination,
            float(self.cfg["playback"]["trailing_silence_seconds"]),
        )
        self._wait_indexed(destination)
        item = self.registry.put(
            name,
            text=text,
            voice=selected_voice,
            filename=filename,
            label=label,
            homebridge=homebridge,
        )
        self.registry.save()
        if item.get("homebridge") or was_homebridge:
            sync_homebridge(self.registry, self.cfg)
        return item

    def retune(
        self,
        name: str,
        text: str,
        *,
        voice: str | None = None,
    ) -> dict[str, Any]:
        """Replace an existing announcement's TTS audio only.

        The existing filename, label and Homebridge registration are preserved,
        and Homebridge reconciliation is deliberately not invoked.
        """
        validate_name(name)
        if not text.strip():
            raise ValueError("Announcement text cannot be empty")

        existing = self.registry.get(name)
        if existing is None:
            raise ValueError(f"No such announcement: {name}")

        selected_voice = voice or existing.get("voice") or self.cfg["tts"]["voice"]
        destination = self.audio_dir / existing["file"]
        try:
            previous_marker = self._index_marker(destination)
        except (MPDError, OSError):
            previous_marker = None

        synthesize_wav(
            text,
            selected_voice,
            destination,
            float(self.cfg["playback"]["trailing_silence_seconds"]),
        )
        self._wait_reindexed(destination, previous_marker)

        item = self.registry.retune(name, text=text, voice=selected_voice)
        self.registry.save()
        return item

    def remove(self, name: str) -> bool:
        validate_name(name)
        old = self.registry.remove(name)
        if old is None:
            return False
        wav = self.audio_dir / old["file"]
        try:
            wav.unlink()
        except FileNotFoundError:
            pass
        self.registry.save()
        if old.get("homebridge"):
            sync_homebridge(self.registry, self.cfg)
        return True
