# Changelog

## 0.1.3 - 2026-09-22

- Temporarily disable repeat/single and consume while the transient announcement item is current, then restore the user's original modes.
- Snapshot the original queue item's URI/path as well as its queue id and reconstruct it if the saved queue entry disappears.
- Never delete the temporary announcement while OwnTone still reports it as the current item, avoiding a blank Remote/player state after a failed restore.
- Apply output-activation retry logic when restoring the original source as well as when starting the announcement.
- Preserve the improved per-output announcement volume handling from 0.1.2.

## 0.1.2 - 2026-09-22

- Poll announcement playback and final player state through MPD instead of repeatedly calling the OwnTone HTTP player endpoint.
- Restore paused sources synchronously: wait for play/seek transitions to settle, then reassert pause until OwnTone reports a stable paused state.
- Make the HTTP-based per-output volume boost best-effort so a transient web API failure cannot prevent an announcement from playing.

## 0.1.1 - 2026-09-22

- Stop triggering full OwnTone library rescans when adding or removing announcements; rely on OwnTone's filesystem watcher instead.
- Publish generated WAV files atomically so OwnTone never sees a half-written announcement.
- Refuse announcement playback while OwnTone reports an active bulk library scan, avoiding queue writes into a busy database.
- Retry announcement start once after an output activation failure; OwnTone deselects receivers that fail activation.
- Preserve genuinely paused playback without an audible unpause by muting untouched selected outputs during play/seek/pause restoration.

## 0.1.0 - 2026-09-22

- Initial packaged release.
- Named announcement registry with `add`, `remove`, `list`, and `play` commands.
- Edge TTS generation and OwnTone library indexing.
- Queue/position restoration and per-output temporary volume floor.
- EOF guard using configurable trailing silence and early restoration.
- Optional managed `homebridge-dummy` switches.
- `alarm-audio NAME` compatibility command for the original alarm setup.
