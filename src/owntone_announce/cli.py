from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import load_config, registry_path
from .homebridge import sync_homebridge
from .mpd import MPDClient
from .owntone import OwnToneHTTP
from .player import AnnouncementPlayer
from .registry import Registry
from .service import AnnouncementService


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="owntone-announce")
    p.add_argument("--config", help="configuration JSON path")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="create or replace a TTS announcement")
    add.add_argument("name")
    add.add_argument("text")
    add.add_argument("--voice")
    add.add_argument("--label", help="Home app display name")
    hb = add.add_mutually_exclusive_group()
    hb.add_argument("--homebridge", dest="homebridge", action="store_true")
    hb.add_argument("--no-homebridge", dest="homebridge", action="store_false")
    add.set_defaults(homebridge=None)

    rm = sub.add_parser("remove", help="remove an announcement")
    rm.add_argument("name")

    play = sub.add_parser("play", help="play an announcement by name")
    play.add_argument("name")

    ls = sub.add_parser("list", help="list configured announcements")
    ls.add_argument("--json", action="store_true", dest="as_json")

    hb_parser = sub.add_parser("homebridge", help="Homebridge Dummy integration")
    hb_sub = hb_parser.add_subparsers(dest="hb_command", required=True)
    sync = hb_sub.add_parser("sync", help="reconcile managed Homebridge Dummy switches")
    restart_group = sync.add_mutually_exclusive_group()
    restart_group.add_argument("--restart", dest="restart", action="store_true")
    restart_group.add_argument("--no-restart", dest="restart", action="store_false")
    sync.set_defaults(restart=None)

    sub.add_parser("doctor", help="check dependencies and OwnTone connectivity")
    return p


def _context(config_arg: str | None):
    cfg = load_config(config_arg)
    registry = Registry(registry_path(cfg))
    return cfg, registry


def _doctor(cfg) -> int:
    failures = 0
    checks: list[tuple[str, bool, str]] = []
    state = Path(cfg["state_dir"])
    audio = Path(cfg["owntone"]["audio_dir"])
    checks.append(("state directory", state.exists(), str(state)))
    checks.append(("audio directory", audio.exists(), str(audio)))
    checks.append(("ffmpeg", shutil.which("ffmpeg") is not None, shutil.which("ffmpeg") or "not found"))

    ow = cfg["owntone"]
    try:
        server = OwnToneHTTP(ow["host"], ow["http_port"]).config()
        build = server.get("buildoptions", [])
        checks.append(("OwnTone HTTP", True, f"version {server.get('version', '?')}"))
        checks.append(("OwnTone MPD build", "MPD" in build, "MPD" if "MPD" in build else "MPD missing"))
    except Exception as exc:
        checks.append(("OwnTone HTTP", False, str(exc)))
    try:
        MPDClient(ow["host"], ow["mpd_port"]).command("status")
        checks.append(("MPD connection", True, f"{ow['host']}:{ow['mpd_port']}"))
    except Exception as exc:
        checks.append(("MPD connection", False, str(exc)))

    hb_path = cfg["homebridge"].get("config_path")
    if hb_path:
        checks.append(("Homebridge config", Path(hb_path).exists(), hb_path))

    for name, ok, detail in checks:
        print(f"{'OK' if ok else 'FAIL':4}  {name}: {detail}")
        failures += 0 if ok else 1
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg, registry = _context(args.config)
        if args.command == "add":
            item = AnnouncementService(cfg, registry).add(
                args.name,
                args.text,
                voice=args.voice,
                label=args.label,
                homebridge=args.homebridge,
            )
            print(f"Added {args.name}: {item['text']}")
            return 0
        if args.command == "remove":
            if AnnouncementService(cfg, registry).remove(args.name):
                print(f"Removed {args.name}")
                return 0
            print(f"No such announcement: {args.name}", file=sys.stderr)
            return 1
        if args.command == "play":
            item = registry.get(args.name)
            if item is None:
                print(f"No such announcement: {args.name}", file=sys.stderr)
                return 2
            wav = Path(cfg["owntone"]["audio_dir"]) / item["file"]
            AnnouncementPlayer(cfg).play(wav)
            return 0
        if args.command == "list":
            if args.as_json:
                print(json.dumps(registry.messages, indent=2, ensure_ascii=False))
            else:
                for name, item in sorted(registry.messages.items()):
                    suffix = " [Homebridge]" if item.get("homebridge") else ""
                    print(f"{name:20} {item.get('text', '')}{suffix}")
            return 0
        if args.command == "homebridge":
            count = sync_homebridge(registry, cfg, restart=args.restart)
            print(f"Synced {count} Homebridge announcement switch(es)")
            return 0
        if args.command == "doctor":
            return _doctor(cfg)
    except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
        print(f"owntone-announce: {exc}", file=sys.stderr)
        return 1
    return 0


def legacy_main() -> int:
    # Compatibility with the original /usr/local/bin/alarm-audio NAME hook.
    if len(sys.argv) != 2:
        print("usage: alarm-audio NAME", file=sys.stderr)
        return 2
    return main(["play", sys.argv[1]])


if __name__ == "__main__":
    raise SystemExit(main())
