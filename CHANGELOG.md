# Changelog

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
