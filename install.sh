#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this installer as root: sudo ./install.sh" >&2
  exit 1
fi

command -v python3 >/dev/null || { echo "python3 not found" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg not found (Debian/Raspberry Pi OS: apt install ffmpeg)" >&2; exit 1; }

PREFIX="${PREFIX:-/opt/owntone-announce}"
VENV="$PREFIX/venv"
ROOT="$(cd "$(dirname "$0")" && pwd)"

install -d -m 0755 "$PREFIX" /etc/owntone-announce /var/lib/owntone-announce /var/owntone/announcements
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install "$ROOT"
ln -sfn "$VENV/bin/owntone-announce" /usr/local/bin/owntone-announce
ln -sfn "$VENV/bin/alarm-audio" /usr/local/bin/alarm-audio

if [[ ! -e /etc/owntone-announce/config.json ]]; then
  install -m 0644 "$ROOT/examples/config.json" /etc/owntone-announce/config.json
fi
if [[ ! -e /var/lib/owntone-announce/messages.json ]]; then
  printf '{\n  "version": 1,\n  "messages": {}\n}\n' > /var/lib/owntone-announce/messages.json
  chmod 0644 /var/lib/owntone-announce/messages.json
fi

cat <<'MSG'
Installed owntone-announce.

Next:
  1. Edit /etc/owntone-announce/config.json if your OwnTone paths/ports differ.
  2. Run: owntone-announce doctor
  3. Add a message, for example:
       sudo owntone-announce add dinner "Dinner is ready"
MSG
