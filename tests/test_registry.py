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
