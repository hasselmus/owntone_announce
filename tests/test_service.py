from pathlib import Path

from owntone_announce.registry import Registry
from owntone_announce.service import AnnouncementService


def test_retune_does_not_sync_homebridge(tmp_path: Path, monkeypatch):
    registry = Registry(tmp_path / "messages.json")
    registry.put(
        "dinner",
        text="Dinner is ready",
        voice="old-voice",
        filename="dinner.wav",
        label="Dinner ready",
        homebridge=True,
    )
    registry.save()

    audio_dir = tmp_path / "audio"
    cfg = {
        "owntone": {
            "host": "127.0.0.1",
            "mpd_port": 6600,
            "audio_dir": str(audio_dir),
        },
        "playback": {"trailing_silence_seconds": 2.0},
        "tts": {"voice": "default-voice"},
    }

    synthesized = []

    def fake_synthesize(text, voice, destination, trailing_silence):
        synthesized.append((text, voice, destination, trailing_silence))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"wav")

    def forbidden_sync(*_args, **_kwargs):
        raise AssertionError("retune must not touch Homebridge")

    monkeypatch.setattr("owntone_announce.service.synthesize_wav", fake_synthesize)
    monkeypatch.setattr("owntone_announce.service.sync_homebridge", forbidden_sync)

    service = AnnouncementService(cfg, registry)
    monkeypatch.setattr(service, "_index_marker", lambda _wav: ("old", "3.0"))
    reindex_calls = []
    monkeypatch.setattr(
        service,
        "_wait_reindexed",
        lambda wav, previous: reindex_calls.append((wav, previous)),
    )

    item = service.retune("dinner", "Dinner in five minutes", voice="new-voice")

    assert synthesized == [
        (
            "Dinner in five minutes",
            "new-voice",
            audio_dir / "dinner.wav",
            2.0,
        )
    ]
    assert reindex_calls == [(audio_dir / "dinner.wav", ("old", "3.0"))]
    assert item["file"] == "dinner.wav"
    assert item["label"] == "Dinner ready"
    assert item["homebridge"] is True

    reloaded = Registry(tmp_path / "messages.json").get("dinner")
    assert reloaded["text"] == "Dinner in five minutes"
    assert reloaded["voice"] == "new-voice"
    assert reloaded["file"] == "dinner.wav"
    assert reloaded["label"] == "Dinner ready"
    assert reloaded["homebridge"] is True


def test_retune_requires_existing_announcement(tmp_path: Path):
    cfg = {
        "owntone": {
            "host": "127.0.0.1",
            "mpd_port": 6600,
            "audio_dir": str(tmp_path / "audio"),
        },
        "playback": {"trailing_silence_seconds": 2.0},
        "tts": {"voice": "default-voice"},
    }
    service = AnnouncementService(cfg, Registry(tmp_path / "messages.json"))

    try:
        service.retune("missing", "Hello")
    except ValueError as exc:
        assert str(exc) == "No such announcement: missing"
    else:
        raise AssertionError("retune should reject unknown announcement names")
