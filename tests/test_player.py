from owntone_announce.mpd import MPDError
from owntone_announce.player import AnnouncementPlayer


class FakeMPD:
    def __init__(self):
        self.calls = 0

    def command(self, command, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            raise MPDError("activation failed")
        return []


class FakeHTTP:
    def __init__(self):
        self.volumes = {"1": 40, "2": 55}
        self.set_calls = []

    def player(self):
        return {"state": "stop", "item_id": None}

    def outputs(self):
        return [
            {"id": "1", "selected": True, "volume": self.volumes["1"]},
            {"id": "2", "selected": True, "volume": self.volumes["2"]},
        ]

    def set_output_volume(self, output_id, volume):
        self.volumes[str(output_id)] = int(volume)
        self.set_calls.append((str(output_id), int(volume)))


def test_start_retries_after_failed_output_activation(monkeypatch):
    player = AnnouncementPlayer.__new__(AnnouncementPlayer)
    player.mpd = FakeMPD()
    player.http = FakeHTTP()
    monkeypatch.setattr("owntone_announce.player.time.sleep", lambda _x: None)

    player._start_announcement(7)
    assert player.mpd.calls == 2


def test_pause_restore_mute_only_unchanged_outputs():
    player = AnnouncementPlayer.__new__(AnnouncementPlayer)
    player.http = FakeHTTP()

    # Output 1 is still at the announcement volume; output 2 was manually changed.
    player.http.volumes["2"] = 60
    state = {"1": (12, 40), "2": (55, 55)}

    muted = player._mute_unchanged_outputs(state)
    assert muted == {"1"}
    assert player.http.volumes["1"] == 0
    assert player.http.volumes["2"] == 60

    player._restore_muted_outputs(state, muted)
    assert player.http.volumes["1"] == 12
    assert player.http.volumes["2"] == 60
