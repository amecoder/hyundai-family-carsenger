from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from scenario.analytics import EventStore
from scenario.family import FamilyHub
from scenario.server import make_server
from tests.test_server import FakeConsole, get, post


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[str, EventStore]]:
    store = EventStore(tmp_path / "a.sqlite", tmp_path / "salt")
    srv = make_server(FakeConsole(), host="127.0.0.1", port=0, sleep=lambda _: threading.Event().wait(0.005),
                      voice_dir=Path("/nonexistent-voice-dir"), analytics=store, family_id="test-family")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    _HUBS[base] = srv.hub
    yield base, store
    _HUBS.pop(base, None)
    srv.runner.stop()
    srv.shutdown()


_HUBS: dict[str, FamilyHub] = {}


def cheers_sent(base: str, n: int = 1) -> None:
    """Cheers waiting for the car, put straight into the hub the way a scenario sends them (no family-side event)."""
    for _ in range(n):
        _HUBS[base].family_cheer("엄마", "응원", "잘 가")


def wait_past_reset(base: str) -> None:
    """A scenario's first step resets the hub, which drops waiting cheers: wait until it has moved on."""
    deadline = time.time() + 5
    while get(base + "/api/status")[1]["runner"]["step_index"] < 1 and time.time() < deadline:
        time.sleep(0.02)


def events(store: EventStore) -> list[tuple[str, str]]:
    return [(r.event, r.source) for r in store.rows()]


def test_consent_is_off_until_the_family_turns_it_on(served: tuple[str, EventStore]) -> None:
    base, store = served
    assert get(base + "/api/analytics")[1]["consent"] is False
    post(base + "/api/family/say", {"sender": "엄마", "text": "잘 가"})
    assert store.count() == 0
    assert post(base + "/api/analytics/consent", {"granted": True}) == (200, {"consent": True})
    post(base + "/api/family/say", {"sender": "엄마", "text": "잘 가"})
    assert events(store) == [("family_message_sent", "live")]


def test_consent_needs_a_boolean(served: tuple[str, EventStore]) -> None:
    base, _ = served
    assert post(base + "/api/analytics/consent", {"granted": "yes"})[0] == 400


def test_family_actions_are_recorded_without_their_content(served: tuple[str, EventStore]) -> None:
    base, store = served
    post(base + "/api/analytics/consent", {"granted": True})
    get(base + "/family")
    post(base + "/api/family/pickup", {"sender": "민지", "place": "수학학원"})
    assert events(store) == [("family_room_opened", "live"), ("pickup_requested", "live")]


def test_car_reports_named_events(served: tuple[str, EventStore]) -> None:
    base, store = served
    post(base + "/api/analytics/consent", {"granted": True})
    assert post(base + "/api/car/event", {"kind": "message", "text": "학원에 도착했어요", "event": "trip_arrived"})[0] == 200
    # family-side names and unknown names from the car are ignored, the message itself still goes through
    post(base + "/api/car/event", {"kind": "message", "text": "x", "event": "cheer_sent"})
    post(base + "/api/car/event", {"kind": "note", "text": "y", "event": "made_up"})
    assert events(store) == [("trip_arrived", "live")]
    assert len(get(base + "/api/family/feed?after=0")[1]["items"]) == 3


def test_events_during_a_scripted_scenario_are_marked_scripted(served: tuple[str, EventStore]) -> None:
    base, store = served
    post(base + "/api/analytics/consent", {"granted": True})
    post(base + "/api/run/pickup")
    wait_past_reset(base)
    cheers_sent(base, 3)
    post(base + "/api/car/event", {"kind": "cheer_played", "text": "엄마: 잘 가", "event": "cheer_played"})
    post(base + "/api/stop")
    deadline = time.time() + 5
    while get(base + "/api/status")[1]["runner"]["state"] == "running" and time.time() < deadline:
        time.sleep(0.05)
    # the car can report a cheer the scenario queued after the runner already stopped: still scripted
    post(base + "/api/car/event", {"kind": "cheer_played", "text": "엄마: 잘 가", "event": "cheer_played"})
    post(base + "/api/manual/door_open")
    time.sleep(0.2)
    # a manual button right after the demo must not wipe the grace window: the queued cheer is still the demo's
    post(base + "/api/car/event", {"kind": "cheer_played", "text": "엄마: 잘 가", "event": "cheer_played"})
    assert events(store) == [("cheer_played", "scripted")] * 3


def test_family_actions_during_a_scripted_scenario_stay_live(served: tuple[str, EventStore]) -> None:
    """A rehearsal is a person using the family app, so it counts as real use even while a demo runs."""
    base, store = served
    post(base + "/api/analytics/consent", {"granted": True})
    post(base + "/api/run/pickup")
    assert get(base + "/api/status")[1]["runner"]["state"] == "running"
    wait_past_reset(base)
    cheers_sent(base)
    get(base + "/family")
    post(base + "/api/family/say", {"sender": "엄마", "text": "잘 가"})
    post(base + "/api/car/event", {"kind": "cheer_played", "text": "엄마: 잘 가", "event": "cheer_played"})
    post(base + "/api/stop")
    deadline = time.time() + 5
    while get(base + "/api/status")[1]["runner"]["state"] == "running" and time.time() < deadline:
        time.sleep(0.05)
    post(base + "/api/family/pickup", {"sender": "민지", "place": "수학학원"})
    assert events(store) == [("family_room_opened", "live"), ("family_message_sent", "live"),
                             ("cheer_played", "scripted"), ("pickup_requested", "live")]


def test_car_reports_after_the_grace_window_are_live(served: tuple[str, EventStore],
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    base, store = served
    monkeypatch.setattr("scenario.server.SCRIPTED_GRACE_S", 0.3)
    post(base + "/api/analytics/consent", {"granted": True})
    post(base + "/api/run/pickup")
    post(base + "/api/stop")
    deadline = time.time() + 5
    while get(base + "/api/status")[1]["runner"]["state"] == "running" and time.time() < deadline:
        time.sleep(0.05)
    post(base + "/api/manual/door_open")
    time.sleep(0.5)
    cheers_sent(base)
    post(base + "/api/car/event", {"kind": "cheer_played", "text": "엄마: 잘 가", "event": "cheer_played"})
    assert events(store) == [("cheer_played", "live")]


def test_core_exchanges_count_only_when_the_family_really_sent_something(served: tuple[str, EventStore]) -> None:
    """A car report of a played cheer or an accepted pickup needs a matching family request, or the North Star inflates."""
    base, store = served
    post(base + "/api/analytics/consent", {"granted": True})
    # nothing was sent: a bug or another local process claiming an exchange is not recorded
    post(base + "/api/car/event", {"kind": "cheer_played", "text": "엄마: 잘 가", "event": "cheer_played"})
    post(base + "/api/car/event", {"kind": "message", "text": "가는 중", "event": "pickup_accepted"})
    assert events(store) == []
    post(base + "/api/family/pickup", {"sender": "민지", "place": "수학학원"})
    post(base + "/api/car/event", {"kind": "message", "text": "가는 중", "event": "pickup_accepted"})
    # one request is answered once: a second answer to the same request is not another exchange
    post(base + "/api/car/event", {"kind": "message", "text": "가는 중", "event": "pickup_accepted"})
    assert events(store) == [("pickup_requested", "live"), ("pickup_accepted", "live")]


def test_withdrawing_consent_deletes_recorded_events(served: tuple[str, EventStore]) -> None:
    base, store = served
    post(base + "/api/analytics/consent", {"granted": True})
    post(base + "/api/family/say", {"sender": "엄마", "text": "잘 가"})
    post(base + "/api/analytics/consent", {"granted": False})
    assert store.count() == 0


def test_retention_report_and_dashboard_page(served: tuple[str, EventStore]) -> None:
    base, _ = served
    post(base + "/api/analytics/consent", {"granted": True})
    cheers_sent(base)
    post(base + "/api/car/event", {"kind": "cheer_played", "text": "엄마: 잘 가", "event": "cheer_played"})
    _, report = get(base + "/api/analytics?weeks=4")
    assert report["consent"] is True
    assert report["retention"]["cohorts"][0]["size"] == 1
    assert report["retention"]["cohorts"][0]["on_or_after"][0] == 1.0
    status, html = get(base + "/analytics")
    assert status == 200 and "재방문율" in html


def test_without_a_store_the_server_still_works() -> None:
    srv = make_server(FakeConsole(), host="127.0.0.1", port=0, voice_dir=Path("/nonexistent-voice-dir"))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert post(base + "/api/family/say", {"sender": "엄마", "text": "잘 가"})[0] == 200
        assert get(base + "/api/analytics")[1] == {"enabled": False}
        assert post(base + "/api/analytics/consent", {"granted": True})[0] == 503
    finally:
        srv.shutdown()


def test_the_family_phone_embedded_in_the_runner_page_is_not_a_visit(served: tuple[str, EventStore]) -> None:
    base, store = served
    post(base + "/api/analytics/consent", {"granted": True})
    get(base + "/family?as=%EC%97%84%EB%A7%88&embed=1")
    assert store.count() == 0
    _, html = get(base + "/")
    assert "/family?as=엄마&embed=1" in html


def test_a_database_error_answers_with_json(served: tuple[str, EventStore]) -> None:
    base, store = served
    store.close()
    status, body = post(base + "/api/analytics/consent", {"granted": True})
    assert status == 500 and "error" in body
    status, body = get_status(base + "/api/analytics")
    assert status == 500
    # the family room itself keeps working
    assert post(base + "/api/family/say", {"sender": "엄마", "text": "잘 가"})[0] == 200


def get_status(url: str) -> tuple[int, dict]:
    import json
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_a_broken_usage_store_does_not_stop_the_demo(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The usage log is optional now that there is no pilot: a damaged key starts the runner without it, loudly."""
    from scenario.server import open_analytics

    (tmp_path / "salt").write_bytes(b"short")  # a key shorter than 32 bytes is refused as damaged
    assert open_analytics(tmp_path / "a.sqlite", tmp_path / "salt") is None
    assert "사용 기록 없이" in caplog.text and "--no-analytics" in caplog.text
    assert isinstance(open_analytics(tmp_path / "b.sqlite", tmp_path / "good-salt"), EventStore)
