from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path
from typing import Any

from .mpd import MPDClient, MPDError, fields, quote
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
        # Track all selected outputs, not only those whose volume changes. That
        # lets paused-state restoration temporarily mute every untouched output.
        #
        # Volume boosting is deliberately best-effort: announcement playback is
        # controlled through MPD and should not fail merely because OwnTone's
        # HTTP API has a transient problem.
        state: dict[str, tuple[int, int]] = {}
        try:
            outputs = self.http.outputs()
        except Exception:
            return state

        try:
            for output in outputs:
                if not output.get("selected"):
                    continue
                output_id = str(output["id"])
                old = int(output.get("volume") or 0)
                temporary = max(old, self.minimum_volume)
                state[output_id] = (old, temporary)
                if temporary != old:
                    self.http.set_output_volume(output_id, temporary)
        except Exception:
            self._restore_output_volumes(state, preserve_manual_changes=False)
            return {}
        return state

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

    def _mute_unchanged_outputs(
        self, volume_state: dict[str, tuple[int, int]]
    ) -> set[str]:
        """Mute outputs whose volume still equals the temporary announcement value."""
        if not volume_state:
            return set()
        try:
            current = {
                str(o["id"]): int(o.get("volume") or 0) for o in self.http.outputs()
            }
        except Exception:
            return set()

        muted: set[str] = set()
        for output_id, (_old, temporary) in volume_state.items():
            if current.get(output_id) != temporary:
                # Assume the user changed this output during the announcement.
                continue
            try:
                self.http.set_output_volume(output_id, 0)
                muted.add(output_id)
            except Exception:
                pass
        return muted

    def _restore_muted_outputs(
        self, volume_state: dict[str, tuple[int, int]], muted: set[str]
    ) -> None:
        if not muted:
            return
        try:
            current = {
                str(o["id"]): int(o.get("volume") or 0) for o in self.http.outputs()
            }
        except Exception:
            current = {}

        for output_id in muted:
            old, _temporary = volume_state[output_id]
            try:
                # If somebody changed the volume in this very small window,
                # respect that manual intervention rather than overwriting it.
                if not current or current.get(output_id) == 0:
                    self.http.set_output_volume(output_id, old)
            except Exception:
                pass

    def _start_item(self, item_id: int, description: str) -> None:
        """Start an item, tolerating one output activation failure."""
        try:
            self.mpd.command(f"playid {item_id}")
            return
        except (MPDError, OSError) as first_error:
            time.sleep(0.25)

            try:
                status = self._status()
                if status.get("songid") == str(item_id) and status.get("state") == "play":
                    return
            except Exception:
                pass

            try:
                if not any(o.get("selected") for o in self.http.outputs()):
                    raise RuntimeError(
                        "No OwnTone outputs remain selected after an output activation failure"
                    ) from first_error
            except RuntimeError:
                raise
            except Exception:
                pass

            try:
                self.mpd.command(f"playid {item_id}")
            except (MPDError, OSError) as second_error:
                raise RuntimeError(
                    f"OwnTone could not start {description} after retrying output activation"
                ) from second_error

    def _start_announcement(self, ann_id: int) -> None:
        self._start_item(ann_id, "the announcement")

    def _status(self) -> dict[str, str]:
        return fields(self.mpd.command("status"))

    def _wait_state(
        self,
        expected: str,
        *,
        song_id: int | None = None,
        timeout: float = 3.0,
        stable_checks: int = 1,
    ) -> dict[str, str]:
        deadline = time.monotonic() + timeout
        stable = 0
        last: dict[str, str] = {}
        while time.monotonic() < deadline:
            last = self._status()
            state_ok = last.get("state") == expected
            song_ok = song_id is None or last.get("songid") == str(song_id)
            if state_ok and song_ok:
                stable += 1
                if stable >= stable_checks:
                    return last
            else:
                stable = 0
            time.sleep(0.10)
        raise RuntimeError(
            f"OwnTone did not settle in state={expected!r}"
            + (f", songid={song_id}" if song_id is not None else "")
            + f"; last status was {last}"
        )

    def _snapshot_current_file(self, song_id: int | None) -> str | None:
        if song_id is None:
            return None
        try:
            return fields(self.mpd.command(f"playlistid {song_id}")).get("file")
        except Exception:
            return None

    def _disable_queue_modes_for_announcement(self, original: dict[str, str]) -> None:
        # Repeat-single would otherwise repeat the temporary announcement, and
        # consume can mutate the queue while the interruption is in progress.
        self.mpd.command("repeat 0", ignore_error=True)
        self.mpd.command("single 0", ignore_error=True)
        self.mpd.command("consume 0", ignore_error=True)

    def _restore_queue_modes(self, original: dict[str, str]) -> None:
        repeat = original.get("repeat", "0") == "1"
        single = original.get("single", "0") == "1"
        consume = original.get("consume", "0") == "1"

        if repeat:
            self.mpd.command("repeat 1", ignore_error=True)
            self.mpd.command(f"single {1 if single else 0}", ignore_error=True)
        else:
            self.mpd.command("repeat 0", ignore_error=True)
            self.mpd.command("single 0", ignore_error=True)
        self.mpd.command(f"consume {1 if consume else 0}", ignore_error=True)

    def _queue_item_exists(self, song_id: int | None) -> bool:
        if song_id is None:
            return False
        try:
            return bool(self.mpd.command(f"playlistid {song_id}"))
        except Exception:
            return False

    def _ensure_original_item(
        self, song_id: int | None, original_file: str | None
    ) -> int | None:
        if self._queue_item_exists(song_id):
            return song_id
        if not original_file:
            return None
        response = fields(self.mpd.command(f"addid {quote(original_file)}"))
        try:
            return int(response["Id"])
        except (KeyError, ValueError):
            return None

    def _restore(
        self,
        state: str,
        song_id: int | None,
        elapsed: float,
        original_file: str | None,
    ) -> int | None:
        if state in ("play", "pause"):
            restore_id = self._ensure_original_item(song_id, original_file)
            if restore_id is None:
                raise RuntimeError("Original OwnTone queue item disappeared and could not be reconstructed")

            self._start_item(restore_id, "the original source")
            self._wait_state("play", song_id=restore_id, timeout=5.0)

            if elapsed > 0.05:
                self.mpd.command(f"seekid {restore_id} {elapsed:.3f}")
                self._wait_state("play", song_id=restore_id, timeout=5.0)

            if state == "pause":
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    status = self._status()
                    if (
                        status.get("state") == "pause"
                        and status.get("songid") == str(restore_id)
                    ):
                        return restore_id
                    if status.get("state") == "play":
                        self.mpd.command("pause 1", ignore_error=True)
                    time.sleep(0.10)
                raise RuntimeError("OwnTone would not return to the original paused state")

            return restore_id

        if state == "stop":
            self.mpd.command("stop", ignore_error=True)
            self._wait_state("stop", timeout=2.0)
        return song_id

    def play(self, wav_path: Path) -> None:
        if not wav_path.exists():
            raise FileNotFoundError(wav_path)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        lock_fd = self._lock()
        try:
            original = fields(self.mpd.command("status"))
            if original.get("updating_db") == "1":
                raise RuntimeError(
                    "OwnTone library scan is in progress; refusing announcement playback "
                    "until the scan completes"
                )
            original_state = original.get("state", "stop")
            original_id: int | None = None
            original_file: str | None = None
            original_elapsed = 0.0
            if original_state != "stop":
                try:
                    original_id = int(original["songid"])
                    original_elapsed = float(original.get("elapsed", "0"))
                except (KeyError, ValueError):
                    original_id = None
                original_file = self._snapshot_current_file(original_id)

            self._disable_queue_modes_for_announcement(original)

            ann_id: int | None = None
            volume_changes: dict[str, tuple[int, int]] = {}
            should_restore = True
            try:
                path = virtual_file_path(wav_path)
                response = fields(self.mpd.command(f"addid {quote(path)}"))
                ann_id = int(response["Id"])
                volume_changes = self._boost_output_volumes()
                self._start_announcement(ann_id)

                deadline = time.monotonic() + self.timeout_seconds
                seen = False
                restore_margin_seconds = self.restore_margin_ms / 1000.0
                while time.monotonic() < deadline:
                    status = self._status()
                    current_id = status.get("songid")
                    state = status.get("state")

                    # OwnTone 29 may still report a queue songid while STOPPED.
                    # Once we have actually observed the announcement playing,
                    # STOPPED means the clip completed even if songid still
                    # happens to equal the temporary queue item's id.
                    if seen && state == "stop":
                        break

                    if current_id == str(ann_id) and state in ("play", "pause"):
                        seen = True
                        length = float(status.get("duration") or 0)
                        progress = float(status.get("elapsed") or 0)
                        if length and progress >= max(0.0, length - restore_margin_seconds):
                            break
                    elif seen:
                        # Another active item means somebody/something changed
                        # playback while the announcement was running.
                        should_restore = False
                        break
                    time.sleep(0.10)
                else:
                    raise TimeoutError("Announcement did not finish before timeout")
            finally:
                restore_error: Exception | None = None
                try:
                    if should_restore and original_state == "pause":
                        # playid/seekid transiently start playback. Keep untouched
                        # outputs muted until the saved source is paused again.
                        muted = self._mute_unchanged_outputs(volume_changes)
                        try:
                            original_id = self._restore(
                                original_state,
                                original_id,
                                original_elapsed,
                                original_file,
                            )
                        finally:
                            self._restore_muted_outputs(volume_changes, muted)
                    else:
                        self._restore_output_volumes(volume_changes)
                        if should_restore:
                            original_id = self._restore(
                                original_state,
                                original_id,
                                original_elapsed,
                                original_file,
                            )
                except Exception as exc:
                    restore_error = exc
                finally:
                    self._restore_queue_modes(original)

                if ann_id is not None:
                    # Never remove the item OwnTone still regards as current.
                    # Deleting the active announcement after a failed restore
                    # produces the blank/non-playing Remote state.
                    try:
                        current = self._status()
                        if (
                            current.get("state") == "stop"
                            or current.get("songid") != str(ann_id)
                        ):
                            self.mpd.command(f"deleteid {ann_id}", ignore_error=True)
                    except Exception:
                        pass

                if restore_error is not None:
                    raise restore_error
        finally:
            os.close(lock_fd)
