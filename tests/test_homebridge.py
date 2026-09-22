from pathlib import Path

from owntone_announce.homebridge import reconcile_homebridge
from owntone_announce.registry import Registry


def test_homebridge_reconcile_preserves_unmanaged(tmp_path: Path):
    reg = Registry(tmp_path / "messages.json")
    reg.put(
        "dinner",
        text="Dinner is ready",
        voice="voice",
        filename="dinner.wav",
        label="Dinner ready",
        homebridge=True,
    )
    data = {
        "platforms": [
            {
                "platform": "HomebridgeDummy",
                "accessories": [
                    {"id": "other", "name": "Other", "type": "Switch"},
                    {"id": "owntone-announce:old", "name": "Old", "type": "Switch"},
                ],
            }
        ]
    }
    hb = {
        "dummy_platform": "HomebridgeDummy",
        "command": "/usr/local/bin/owntone-announce",
        "auto_reset_ms": 500,
    }
    out = reconcile_homebridge(data, reg, hb)
    accessories = out["platforms"][0]["accessories"]
    assert accessories[0]["id"] == "other"
    assert accessories[1]["id"] == "owntone-announce:dinner"
    assert accessories[1]["commandOn"] == "/usr/local/bin/owntone-announce play dinner"
    assert accessories[1]["autoReset"]["time"] == 500
