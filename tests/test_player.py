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
    assert player.mpd.calls == 3


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


class SequenceMPD:
    def __init__(self):
        self.commands = []
        self.statuses = [
            ["state: play", "songid: 9"],
            ["state: play", "songid: 9"],
            ["state: play", "songid: 9"],
            ["state: pause", "songid: 9"],
        ]

    def command(self, command, **_kwargs):
        self.commands.append(command)
        if command == "playlistid 9":
            return ["file: file:/music/ambient.wav", "Id: 9"]
        if command == "status":
            return self.statuses.pop(0)
        return []


def test_restore_paused_waits_for_play_then_reasserts_pause(monkeypatch):
    player = AnnouncementPlayer.__new__(AnnouncementPlayer)
    player.mpd = SequenceMPD()
    monkeypatch.setattr("owntone_announce.player.time.sleep", lambda _x: None)

    player.http = FakeHTTP()
    player._restore("pause", 9, 12.5, "file:/music/ambient.wav")

    assert player.mpd.commands[:4] == [
        "playlistid 9",
        "playid 9",
        "status",
        "seekid 9 12.500",
    ]
    assert "pause 1" in player.mpd.commands


class BrokenHTTP:
    def outputs(self):
        raise OSError("transient http failure")


def test_volume_boost_is_best_effort():
    player = AnnouncementPlayer.__new__(AnnouncementPlayer)
    player.http = BrokenHTTP()
    player.minimum_volume = 40

    assert player._boost_output_volumes() == {}


class RecordingMPD:
    def __init__(self, responses=None):
        self.commands = []
        self.responses = responses or {}

    def command(self, command, **_kwargs):
        self.commands.append(command)
        value = self.responses.get(command, [])
        return value() if callable(value) else value


def test_repeat_single_and_consume_are_temporarily_disabled_and_restored():
    player = AnnouncementPlayer.__new__(AnnouncementPlayer)
    player.mpd = RecordingMPD()
    original = {"repeat": "1", "single": "1", "consume": "1"}

    player._disable_queue_modes_for_announcement(original)
    player._restore_queue_modes(original)

    assert player.mpd.commands == [
        "repeat 0",
        "single 0",
        "consume 0",
        "repeat 1",
        "single 1",
        "consume 1",
    ]


def test_original_item_is_readded_from_saved_uri_if_queue_id_disappears():
    player = AnnouncementPlayer.__new__(AnnouncementPlayer)
    player.mpd = RecordingMPD(
        {
            "playlistid 9": [],
            'addid "file:/music/ambient.wav"': ["Id: 42"],
        }
    )

    assert player._ensure_original_item(9, "file:/music/ambient.wav") == 42
    assert player.mpd.commands == [
        "playlistid 9",
        'addid "file:/music/ambient.wav"',
    ]
