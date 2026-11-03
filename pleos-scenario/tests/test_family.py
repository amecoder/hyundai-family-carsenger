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


def test_cheer_shows_in_chat_and_reaches_the_car_with_one_id() -> None:
    hub = FamilyHub()
    cheer_id = hub.family_cheer("엄마", "응원 음성 \"장 보느라 고생해\"", "장 보느라 고생해", audio_id="a1")
    item = hub.feed_after(0)["items"][-1]
    assert (item["kind"], item["sender"], item["cheer_id"]) == ("family", "엄마", cheer_id)
    cmd = hub.commands_after(0)["commands"][-1]
    assert (cmd["type"], cmd["from"], cmd["text"], cmd["audio_id"]) == ("cheer", "엄마", "장 보느라 고생해", "a1")


def test_played_cheer_is_matched_to_the_oldest_waiting_one() -> None:
    hub = FamilyHub()
    first = hub.family_cheer("민지", "a", "아빠 최고!")
    second = hub.family_cheer("민지", "b", "아빠 최고!")
    hub.car_event("cheer_played", "민지: 아빠 최고!")
    hub.car_event("cheer_played", "민지: 아빠 최고!")
    hub.car_event("cheer_played", "민지: 모르는 응원")
    played = [i for i in hub.feed_after(0)["items"] if i["kind"] == "cheer_played"]
    assert [i.get("cheer_id") for i in played] == [first, second, None]


def test_reset_forgets_waiting_cheers() -> None:
    hub = FamilyHub()
    hub.family_cheer("엄마", "a", "우유도 잊지 마")
    hub.reset()
    hub.car_event("cheer_played", "엄마: 우유도 잊지 마")
    assert "cheer_id" not in hub.feed_after(0)["items"][-1]


def test_sound_log_keeps_car_speech_and_first_clip_fetch_with_time() -> None:
    now = iter([10.0, 11.5, 12.0, 13.0])
    hub = FamilyHub(clock=lambda: next(now))
    hub.car_event("speak", "경유지로 추가할까요?")
    hub.car_event("message", "가족방 글은 소리가 아님")
    clip = hub.add_audio(b"RIFF", "audio/wav")
    hub.audio_served(clip)
    hub.audio_served(clip)  # the player may fetch the same clip again; it is still one sound
    assert hub.sounds_since(0) == [{"ts": 10.0, "kind": "speech", "text": "경유지로 추가할까요?"},
                                   {"ts": 11.5, "kind": "clip", "audio_id": clip}]
    assert hub.sounds_since(11.0) == [{"ts": 11.5, "kind": "clip", "audio_id": clip}]


def test_a_skipped_cheer_leaves_the_queue_and_tells_the_family() -> None:
    # with cheers off in the car the cheer is not played; it must not stay waiting and catch a later identical cheer
    hub = FamilyHub()
    skipped = hub.family_cheer("엄마", "a", "천천히 와도 돼")
    later = hub.family_cheer("엄마", "b", "천천히 와도 돼")
    assert hub.car_event("cheer_skipped", "엄마: 천천히 와도 돼") is True
    assert hub.car_event("cheer_played", "엄마: 천천히 와도 돼") is True
    items = hub.feed_after(0)["items"]
    assert [(i["kind"], i.get("cheer_id")) for i in items if i["kind"] in {"cheer_skipped", "cheer_played"}] == [
        ("cheer_skipped", skipped), ("cheer_played", later)]
    assert hub.car_event("cheer_played", "엄마: 천천히 와도 돼") is False  # nothing left waiting


def test_each_pickup_request_is_answered_once_and_reset_closes_it() -> None:
    hub = FamilyHub()
    assert hub.answer_pickup() is False
    hub.add_command("pickup_request", by="민지", place="학원", eta_min=12)
    assert hub.answer_pickup() is True
    assert hub.answer_pickup() is False
    hub.add_command("pickup_request", by="민지", place="학원", eta_min=12)
    hub.reset()
    assert hub.answer_pickup() is False  # a timeout for a request from before the reset is not counted
