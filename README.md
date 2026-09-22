# owntone-announce

Small Linux/Raspberry Pi utility for spoken announcements through an existing
[OwnTone](https://owntone.github.io/owntone-server/) multi-room audio setup.

It grew out of a Homebridge alarm-announcement setup, but the package is generic:
messages live in one registry and can be created, removed and played by name.

```text
owntone-announce add dinner "Dinner is ready"
owntone-announce play dinner
owntone-announce remove dinner
```

`add` uses Microsoft Edge neural TTS through `edge-tts`, converts the result to a
local WAV, asks OwnTone to index it, and records it in the registry. Playback is
local after generation; an Internet connection is only needed while generating
new TTS audio.

## What it does

When an announcement is played, `owntone-announce`:

1. remembers OwnTone's current queue item, playback state and position;
2. adds the announcement as a temporary queue item;
3. temporarily raises the volume of currently selected outputs to a configurable
   minimum;
4. plays the WAV through the outputs already selected in OwnTone;
5. restores those output volumes (unless they were manually changed meanwhile);
6. returns to the previous queue item and position; and
7. removes the temporary queue item.

It deliberately does **not** choose speakers for you. The current OwnTone output
selection remains authoritative.

The generated WAV contains trailing silence. Playback switches back before the
physical end of the file, avoiding the short EOF/restart artefact some OwnTone /
AirPlay combinations otherwise produce.

## Requirements

- Linux (developed on Raspberry Pi OS)
- Python 3.9+
- OwnTone with MPD support enabled (default MPD port 6600)
- `ffmpeg`
- network access when generating TTS

The default paths assume `/var/owntone` is one of OwnTone's indexed library
roots. Change `audio_dir` if yours differs.

## Installation

On Debian / Raspberry Pi OS:

```bash
sudo apt install python3-venv ffmpeg
git clone https://github.com/hasselmus/owntone_announce.git
cd owntone_announce
sudo bash install.sh
owntone-announce doctor
```

The installer creates an isolated venv under `/opt/owntone-announce`, installs
`owntone-announce` and the backwards-compatible `alarm-audio` command in
`/usr/local/bin`, and installs a default configuration at:

```text
/etc/owntone-announce/config.json
```

Runtime state is kept in:

```text
/var/lib/owntone-announce/messages.json
```

The registry is intentionally outside the Git checkout so Stockholm, Lund, or
other installations can use the same code with different local messages and
configuration.

## Commands

Create or replace a message:

```bash
sudo owntone-announce add dinner "Dinner is ready"
```

Use another Edge TTS voice:

```bash
sudo owntone-announce add dinner "Dinner is ready" --voice en-GB-RyanNeural
```

Play it:

```bash
owntone-announce play dinner
```

List messages:

```bash
owntone-announce list
```

Remove one:

```bash
sudo owntone-announce remove dinner
```

Names are deliberately shell-friendly and may contain lowercase letters,
numbers, `_` and `-`.

## Configuration

Example `/etc/owntone-announce/config.json`:

```json
{
  "owntone": {
    "host": "127.0.0.1",
    "http_port": 3689,
    "mpd_port": 6600,
    "audio_dir": "/var/owntone/announcements"
  },
  "playback": {
    "minimum_volume": 40,
    "trailing_silence_seconds": 2.0,
    "restore_margin_seconds": 1.0,
    "timeout_seconds": 30
  },
  "tts": {
    "voice": "en-GB-SoniaNeural"
  },
  "state_dir": "/var/lib/owntone-announce",
  "homebridge": {
    "config_path": null,
    "dummy_platform": "HomebridgeDummy",
    "command": "/usr/local/bin/owntone-announce",
    "auto_reset_ms": 500,
    "restart_on_sync": false,
    "restart_command": ["hb-service", "restart"]
  }
}
```

`trailing_silence_seconds - restore_margin_seconds` is approximately the audible
pause between the end of speech and resuming the previous programme. The defaults
therefore give about one second of audible silence and one second of unused EOF
guard.

Set `OWNTONE_ANNOUNCE_CONFIG` or pass `--config` to use another configuration.

## Homebridge / Apple Home

Optional integration uses the maintained `homebridge-dummy` plugin rather than
shipping another Homebridge plugin.

Configure its path once, for example:

```json
"homebridge": {
  "config_path": "/var/lib/homebridge/config.json",
  "dummy_platform": "HomebridgeDummy",
  "command": "/usr/local/bin/owntone-announce",
  "auto_reset_ms": 500,
  "restart_on_sync": true,
  "restart_command": ["hb-service", "restart"]
}
```

Then one command creates the TTS message **and** its momentary Apple Home switch:

```bash
sudo owntone-announce add dinner "Dinner is ready" \
  --homebridge --label "Dinner ready"
```

Removing the message removes its managed Homebridge switch as well:

```bash
sudo owntone-announce remove dinner
```

You can reconcile Homebridge explicitly at any time:

```bash
sudo owntone-announce homebridge sync
sudo owntone-announce homebridge sync --restart
```

Only `homebridge-dummy` accessories whose `id` begins with
`owntone-announce:` are managed. Other dummy switches are preserved. Before each
write, the utility copies the Homebridge configuration to
`config.json.owntone-announce.bak`.

Homebridge integration requires the modern platform-style `homebridge-dummy`
configuration (`platform: "HomebridgeDummy"`). The plugin itself must already be
installed and configured.

## Alarm / existing installations

The package provides an `alarm-audio` compatibility entry point, so existing
Homebridge hooks such as:

```text
/usr/local/bin/alarm-audio arming
```

continue to work. It is equivalent to:

```text
/usr/local/bin/owntone-announce play arming
```

Migrate the original five alarm phrases into the registry with:

```bash
sudo owntone-announce add arming \
  "Alarm arming. You have thirty seconds to leave."
sudo owntone-announce add armed "Alarm armed."
sudo owntone-announce add disarmed "Alarm disarmed."
sudo owntone-announce add warning \
  "Warning. The alarm will trigger in thirty seconds."
sudo owntone-announce add triggered "Alarm triggered."
```

These should normally *not* use `--homebridge`: the security-system plugin
already invokes them at the appropriate state transitions.

For safety, `install.sh` preserves an existing non-symlink `/usr/local/bin/alarm-audio`
instead of replacing a working legacy alarm hook before these messages exist. After
adding and testing the registry entries, switch the old command to the packaged
compatibility entry point:

```bash
sudo ln -sfn /opt/owntone-announce/venv/bin/alarm-audio /usr/local/bin/alarm-audio
```

## Behaviour and limitations

### Spotify / competing speaker sessions

An announcement makes OwnTone take control of its selected output devices. If a
physical speaker is simultaneously being used by Spotify Connect (or another
renderer), taking that speaker can pause Spotify or detach that speaker from its
Spotify group. This is a property of the output device/session, not the message
registry.

For speakers that should never receive OwnTone audio, exclude them in
`owntone.conf` with the normal per-device `exclude = true` setting.

### No selected OwnTone outputs

The utility does not select a fallback speaker. If OwnTone has no usable output
selected, it does not invent one.

### TTS privacy / availability

`edge-tts` uses Microsoft's online speech service. The text supplied to `add` is
sent to that service during synthesis. Playback later uses the locally generated
WAV and does not require the TTS service.

### Queue restoration

Seekable tracks resume near their previous position. A non-seekable stream may
restart because OwnTone/MPD cannot seek it.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e . pytest
pytest -q
```

The runtime implementation intentionally uses the Python standard library for
OwnTone HTTP/MPD communication. `edge-tts` is the only Python runtime dependency;
`ffmpeg` performs audio conversion.

## License

MIT.
