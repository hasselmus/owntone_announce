from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path
from typing import Any

from .mpd import MPDClient, fields, quote
from .owntone import OwnToneHTTP, virtual_file_path


class AnnouncementPlayer:
    def __init__(self, cfg: dict[str, Any]):
        ow = cfg["owntone"]
        pb = cfg["playback"]
        self.mpd = MPDClient(ow["host"], int(ow["mpd_port"]))
        self.http = OwnToneHTTP(ow["host"], int(ow["http_port"]))
        self.minimum_volume = int(pb["minimum_volume"])
        self.restore_margin_ms = int(float(pb["restore_margin_seconds"]) * 1000)
        self.timeout_seconds = float(pb["timeout_seconds"])
        self.state_dir = Path(cfg["state_dir"])

    def _lock(self) -> int:
        # Lock the directory inode itself. It is stable across users and avoids
        # a world-writable lock file created by whichever account runs first.
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        fd = os.open(self.state_dir, flags)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _boost_output_volumes(self) -> dict[str, tuple[int, int]]:
        changed: dict[str, tuple[int, int]] = {}
        try:
            for output in self.http.outputs():
                if not output.get("selected"):
                    continue
                output_id = str(output["id"])
                old = int(output.get("volume") or 0)
                temporary = max(old, self.minimum_volume)
                if temporary != old:
                    self.http.set_output_volume(output_id, temporary)
                    changed[output_id] = (old, temporary)
        except Exception:
            self._restore_output_volumes(changed, preserve_manual_changes=False)
            raise
        return changed

    def _restore_output_volumes(
        self, changed: dict[str, tuple[int, int]], preserve_manual_changes: bool = True
    ) -> None:
        if not changed:
            return
        current = None
        if preserve_manual_changes:
            try:
                current = {
                    str(o["id"]): int(o.get("volume") or 0) for o in self.http.outputs()
                }
            except Exception:
                current = None

        for output_id, (old, temporary) in changed.items():
            try:
                if current is None or current.get(output_id) == temporary:
                    self.http.set_output_volume(output_id, old)
            except Exception:
                pass

    def _restore(self, state: str, song_id: int | None, elapsed: float) -> None:
        if state in ("play", "pause") and song_id is not None:
            self.mpd.command(f"playid {song_id}", ignore_error=True)
            if elapsed > 0.05:
                self.mpd.command(f"seekid {song_id} {elapsed:.3f}", ignore_error=True)
            if state == "pause":
                self.mpd.command("pause 1", ignore_error=True)
        elif state == "stop":
            self.mpd.command("stop", ignore_error=True)

    def play(self, wav_path: Path) -> None:
        if not wav_path.exists():
            raise FileNotFoundError(wav_path)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        lock_fd = self._lock()
        try:
            original = fields(self.mpd.command("status"))
            original_state = original.get("state", "stop")
            original_id: int | None = None
            original_elapsed = 0.0
            if original_state != "stop":
                try:
                    original_id = int(original["songid"])
                    original_elapsed = float(original.get("elapsed", "0"))
                except (KeyError, ValueError):
                    original_id = None

            ann_id: int | None = None
            volume_changes: dict[str, tuple[int, int]] = {}
            should_restore = True
            try:
                path = virtual_file_path(wav_path)
                response = fields(self.mpd.command(f"addid {quote(path)}"))
                ann_id = int(response["Id"])
                volume_changes = self._boost_output_volumes()
                self.mpd.command(f"playid {ann_id}")

                deadline = time.monotonic() + self.timeout_seconds
                seen = False
                while time.monotonic() < deadline:
                    status = self.http.player()
                    current_id = status.get("item_id")
                    if current_id == ann_id:
                        seen = True
                        length = int(status.get("item_length_ms") or 0)
                        progress = int(status.get("item_progress_ms") or 0)
                        if length and progress >= max(0, length - self.restore_margin_ms):
                            break
                    elif seen:
                        # Respect apparent manual intervention while announcing.
                        should_restore = False
                        break
                    time.sleep(0.10)
                else:
                    raise TimeoutError("Announcement did not finish before timeout")
            finally:
                self._restore_output_volumes(volume_changes)
                if should_restore:
                    self._restore(original_state, original_id, original_elapsed)
                if ann_id is not None:
                    self.mpd.command(f"deleteid {ann_id}", ignore_error=True)
        finally:
            os.close(lock_fd)
