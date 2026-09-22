from owntone_announce.mpd import fields, quote


def test_quote():
    assert quote('a"b\\c') == '"a\\"b\\\\c"'


def test_fields():
    assert fields(["state: play", "songid: 3"]) == {"state": "play", "songid": "3"}
