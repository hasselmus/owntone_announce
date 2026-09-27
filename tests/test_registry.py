from pathlib import Path

from owntone_announce.registry import Registry


def test_registry_roundtrip(tmp_path: Path):
    path = tmp_path / "messages.json"
    reg = Registry(path)
    reg.put("dinner", text="Dinner is ready", voice="voice", filename="dinner.wav", homebridge=True)
    reg.save()

    loaded = Registry(path)
    assert loaded.get("dinner")["text"] == "Dinner is ready"
    assert loaded.get("dinner")["homebridge"] is True
    assert loaded.remove("dinner") is not None


def test_retune_preserves_registration_fields(tmp_path: Path):
    path = tmp_path / "messages.json"
    reg = Registry(path)
    reg.put(
        "dinner",
        text="Dinner is ready",
        voice="old-voice",
        filename="custom-dinner.wav",
        label="Dinner ready",
        homebridge=True,
    )

    item = reg.retune("dinner", text="Dinner in five minutes", voice="new-voice")

    assert item == {
        "text": "Dinner in five minutes",
        "voice": "new-voice",
        "file": "custom-dinner.wav",
        "label": "Dinner ready",
        "homebridge": True,
    }
