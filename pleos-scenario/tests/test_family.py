from __future__ import annotations

import pytest

from scenario.family import MAX_AUDIO_BYTES, MAX_AUDIO_CLIPS, FamilyHub


def test_commands_are_sequenced_and_filtered_by_cursor() -> None:
    hub = FamilyHub()
    hub.add_command("set_trip", destination="집", eta_min=40)
    hub.add_command("pickup_request", by="민지", place="학원", eta_min=12)
    out = hub.commands_after(0)
    assert [c["type"] for c in out["commands"]] == ["set_trip", "pickup_request"]
    assert out["commands"][1]["by"] == "민지"
    assert out["reset_cursor"] is False
    assert hub.commands_after(out["commands"][-1]["seq"])["commands"] == []


def test_reset_clears_and_tells_stale_cursor_to_restart() -> None:
    hub = FamilyHub()
    for i in range(5):
        hub.add_command("cheer", text=str(i))
    hub.reset()
    hub.add_command("reset")
    out = hub.commands_after(5)
    assert out["reset_cursor"] is True
    assert [c["type"] for c in out["commands"]] == ["reset"]


def test_car_events_and_family_messages_share_one_feed() -> None:
    hub = FamilyHub()
    hub.car_event("message", "아빠 출발, 40분 뒤 집 도착 예정")
    hub.family_says("민지", "데리러 와")
    hub.car_event("speak", "경유지로 추가할까요?")
    items = hub.feed_after(0)["items"]
    assert [(i["kind"], i["sender"]) for i in items] == [("message", "차"), ("family", "민지"), ("speak", "차")]
    assert hub.feed_after(items[0]["seq"])["items"][0]["kind"] == "family"


def test_unknown_car_event_kind_is_kept_as_note() -> None:
    hub = FamilyHub()
    hub.car_event("weird", "x")
    assert hub.feed_after(0)["items"][0]["kind"] == "note"


def test_feed_reset_flag_after_hub_reset() -> None:
    hub = FamilyHub()
    hub.car_event("message", "a")
    hub.car_event("message", "b")
    hub.reset()
    out = hub.feed_after(2)
    assert out["reset"] is True and out["items"] == []


def test_negative_cursor_means_start_from_now() -> None:
    hub = FamilyHub()
    hub.add_command("cheer", text="old")
    hub.add_command("cheer", text="older")
    out = hub.commands_after(-1)
    assert out["commands"] == []
    assert out["cursor"] == 2
    hub.add_command("pickup_request")
    assert [c["type"] for c in hub.commands_after(out["cursor"])["commands"]] == ["pickup_request"]


def test_audio_clip_is_stored_and_served_back() -> None:
    hub = FamilyHub()
    clip_id = hub.add_audio(b"OggS-voice", "audio/webm;codecs=opus")
    assert hub.audio(clip_id) == (b"OggS-voice", "audio/webm;codecs=opus")
    assert hub.audio("missing") is None


def test_audio_rejects_non_audio_and_oversized_clips() -> None:
    hub = FamilyHub()
    with pytest.raises(ValueError, match="음성"):
        hub.add_audio(b"<html>", "text/html")
    with pytest.raises(ValueError, match="2MB"):
        hub.add_audio(b"x" * (MAX_AUDIO_BYTES + 1), "audio/webm")
    with pytest.raises(ValueError, match="비어"):
        hub.add_audio(b"", "audio/webm")


def test_audio_store_keeps_only_the_newest_clips() -> None:
    hub = FamilyHub()
    ids = [hub.add_audio(bytes([i]), "audio/webm") for i in range(MAX_AUDIO_CLIPS + 2)]
    assert hub.audio(ids[0]) is None and hub.audio(ids[1]) is None
    assert hub.audio(ids[-1]) == (bytes([MAX_AUDIO_CLIPS + 1]), "audio/webm")


def test_cursor_from_before_a_reset_gets_everything_after_it() -> None:
    # same number of commands before and after the reset: a car whose cursor equals the old count must not miss them
    hub = FamilyHub()
    hub.add_command("reset")
    hub.add_command("set_trip")
    cursor = hub.commands_after(0)["cursor"]
    hub.reset()
    hub.add_command("reset")
    hub.add_command("set_trip")
    out = hub.commands_after(cursor)
    assert out["reset_cursor"] is True
    assert [c["type"] for c in out["commands"]] == ["reset", "set_trip"]
    assert hub.commands_after(out["cursor"])["commands"] == []


def test_feed_cursor_from_before_a_reset_is_told_to_start_over() -> None:
    hub = FamilyHub()
    hub.car_event("message", "a")
    hub.family_says("민지", "b")
    hub.reset()
    hub.car_event("message", "c")
    hub.family_says("민지", "d")
    out = hub.feed_after(2)
    assert out["reset"] is True
    assert [i["text"] for i in hub.feed_after(0)["items"]] == ["c", "d"]
