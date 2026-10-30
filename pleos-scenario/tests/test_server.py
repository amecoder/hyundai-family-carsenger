from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from scenario.screen import ScreenGrabber
from scenario.server import make_server
from tests.test_runner import RecordingClient


class FakeConsole(RecordingClient):
    def __init__(self, fail_state: bool = False) -> None:
        super().__init__()
        self.fail_state = fail_state

    def state(self) -> dict[str, Any]:
        if self.fail_state:
            raise RuntimeError("Virtual Console에 연결할 수 없습니다")
        return {
            "gear": {"actual": {"value": "Drive"}},
            "controls": {"speed_kph": 42},
            "body": {"doors": {"rear_left": True, "rear_right": False}, "door_locks": {"all": False}},
            "seat": {"occupied": {"rear_left": True, "rear_right": False}},
            "ev_battery": {"state_of_charge": 80.0},
        }


def _serve(console: FakeConsole, grabber: ScreenGrabber | None = None, voice_dir: Path | None = None) -> Iterator[str]:
    srv = make_server(console, host="127.0.0.1", port=0, sleep=lambda _: threading.Event().wait(0.005), grabber=grabber,
                      voice_dir=voice_dir or Path("/nonexistent-voice-dir"))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.runner.stop()
    srv.shutdown()


@pytest.fixture
def base() -> Iterator[str]:
    yield from _serve(FakeConsole())


def get(url: str) -> tuple[int, Any]:
    with urllib.request.urlopen(url, timeout=5) as r:
        body = r.read()
        ctype = r.headers.get("Content-Type", "")
        return r.status, json.loads(body) if "json" in ctype else body.decode()


def post(url: str, body: dict | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(url, method="POST", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_index_page_is_served_in_korean(base: str) -> None:
    status, html = get(base + "/")
    assert status == 200
    assert "현대 패밀리 카신저 시나리오 실행기" in html


def test_scenarios_list_includes_steps(base: str) -> None:
    _, data = get(base + "/api/scenarios")
    pickup = next(s for s in data if s["id"] == "pickup")
    assert pickup["title"] == "평일 학원 픽업"
    assert pickup["steps"][0]["title"].startswith("준비")
    assert {"title", "narration", "expect"} <= set(pickup["steps"][1])


def test_status_summarizes_vehicle(base: str) -> None:
    _, data = get(base + "/api/status")
    assert data["runner"]["state"] == "idle"
    assert data["vehicle"] == {
        "gear": "Drive", "speed_kph": 42, "door_rear_left": True, "door_rear_right": False,
        "seat_rear_left": True, "seat_rear_right": False, "doors_locked": False, "soc": 80.0,
    }
    assert data["vehicle_error"] is None


def test_run_unknown_scenario_returns_404(base: str) -> None:
    status, data = post(base + "/api/run/nope")
    assert status == 404
    assert "없는 시나리오" in data["error"]


def test_run_then_stop(base: str) -> None:
    status, _ = post(base + "/api/run/long_drive")
    assert status == 200
    status, data = post(base + "/api/run/pickup")
    assert status == 409
    assert "실행 중" in data["error"]
    post(base + "/api/stop")
    st: dict = {}
    for _ in range(200):
        _, st = get(base + "/api/status")
        if st["runner"]["state"] != "running":
            break
        threading.Event().wait(0.02)
    assert st["runner"]["state"] in {"stopped", "done"}


def test_status_reports_console_errors_without_crashing() -> None:
    gen = _serve(FakeConsole(fail_state=True))
    url = next(gen)
    _, data = get(url + "/api/status")
    assert data["vehicle"] is None
    assert "연결할 수 없습니다" in data["vehicle_error"]
    next(gen, None)


def test_car_event_appears_in_family_feed(base: str) -> None:
    status, _ = post(base + "/api/car/event", {"kind": "message", "text": "아빠 출발"})
    assert status == 200
    _, feed = get(base + "/api/family/feed?after=0")
    assert feed["items"][-1]["text"] == "아빠 출발"
    assert feed["items"][-1]["kind"] == "message"


def test_bad_car_event_is_rejected(base: str) -> None:
    status, data = post(base + "/api/car/event", {"kind": "message"})
    assert status == 400
    assert "text" in data["error"]


def test_scenario_feeds_car_inbox_and_family_chat(base: str) -> None:
    post(base + "/api/run/pickup")
    seen: set[str] = set()
    for _ in range(400):
        _, inbox = get(base + "/api/car/inbox?after=0")
        seen = {c["type"] for c in inbox["commands"]}
        if "pickup_request" in seen:
            break
        threading.Event().wait(0.01)
    assert {"reset", "set_trip", "pickup_request"} <= seen
    _, feed = get(base + "/api/family/feed?after=0")
    assert any(i["kind"] == "family" and i["sender"] == "민지" for i in feed["items"])
    post(base + "/api/stop")


def test_screen_endpoint_serves_latest_frame() -> None:
    g = ScreenGrabber(lambda: b"\x89PNG-frame", interval=0.01, idle_timeout=1, resize=None)
    gen = _serve(FakeConsole(), grabber=g)
    url = next(gen)
    for _ in range(100):
        try:
            with urllib.request.urlopen(url + "/api/screen", timeout=5) as r:
                if r.status == 200:
                    assert r.read() == b"\x89PNG-frame"
                    assert r.headers["Content-Type"] == "image/png"
                    break
        except urllib.error.HTTPError as e:
            assert e.code == 503
        threading.Event().wait(0.02)
    else:
        raise AssertionError("no frame served")
    g.stop()
    next(gen, None)


def test_summarize_tolerates_null_sections_before_bridge_is_ready() -> None:
    from scenario.server import summarize

    # right after boot Virtual Console reports keys with null values until a browser session arrives
    state = {"gear": {"bridge_ready": False, "actual": None}, "controls": None, "body": {"doors": None},
             "seat": {"occupied": None}, "ev_battery": None}
    assert summarize(state) == {"gear": None, "speed_kph": None, "door_rear_left": None, "door_rear_right": None,
                                "seat_rear_left": None, "seat_rear_right": None, "doors_locked": None, "soc": None}


def post_raw(url: str, data: bytes, ctype: str) -> tuple[int, Any]:
    req = urllib.request.Request(url, method="POST", data=data, headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def inbox_types(base: str) -> list[str]:
    _, inbox = get(base + "/api/car/inbox?after=0")
    return [c["type"] for c in inbox["commands"]]


def test_family_page_is_served(base: str) -> None:
    status, html = get(base + "/family")
    assert status == 200
    assert "가족방" in html


def test_family_text_goes_to_chat_only_never_to_the_car(base: str) -> None:
    status, _ = post(base + "/api/family/say", {"sender": "엄마", "text": "저녁 뭐 먹을래?"})
    assert status == 200
    _, feed = get(base + "/api/family/feed?after=0")
    assert feed["items"][-1] == {**feed["items"][-1], "kind": "family", "sender": "엄마", "text": "저녁 뭐 먹을래?"}
    assert inbox_types(base) == []


@pytest.mark.parametrize("body", [
    {"sender": "모르는사람", "text": "안녕"},
    {"sender": "엄마", "text": "   "},
    {"sender": "엄마", "text": "가" * 301},
    {"sender": "엄마"},
])
def test_family_text_is_validated(base: str, body: dict) -> None:
    status, data = post(base + "/api/family/say", body)
    assert status == 400
    assert data["error"]


def test_family_pickup_request_reaches_car_inbox(base: str) -> None:
    status, _ = post(base + "/api/family/pickup", {"sender": "민지", "place": "○○수학학원 앞"})
    assert status == 200
    _, inbox = get(base + "/api/car/inbox?after=0")
    cmd = inbox["commands"][-1]
    assert (cmd["type"], cmd["by"], cmd["place"], cmd["eta_min"]) == ("pickup_request", "민지", "○○수학학원 앞", 12)
    _, feed = get(base + "/api/family/feed?after=0")
    assert "○○수학학원 앞" in feed["items"][-1]["text"]


def test_family_pickup_needs_a_place(base: str) -> None:
    status, _ = post(base + "/api/family/pickup", {"sender": "민지", "place": ""})
    assert status == 400


def test_recorded_cheer_is_stored_and_sent_to_car(base: str) -> None:
    from urllib.parse import quote

    url = f"{base}/api/family/cheer?sender={quote('엄마')}&text={quote('조심히 와')}&duration_ms=4200"
    status, data = post_raw(url, b"\x1aE\xdf\xa3voice", "audio/webm;codecs=opus")
    assert status == 200
    _, inbox = get(base + "/api/car/inbox?after=0")
    cmd = inbox["commands"][-1]
    assert (cmd["type"], cmd["from"], cmd["text"], cmd["audio_id"], cmd["duration_ms"]) == (
        "cheer", "엄마", "조심히 와", data["audio_id"], 4200)
    with urllib.request.urlopen(f"{base}/api/audio/{data['audio_id']}", timeout=5) as r:
        assert r.read() == b"\x1aE\xdf\xa3voice"
        assert r.headers["Content-Type"] == "audio/webm;codecs=opus"
    _, feed = get(base + "/api/family/feed?after=0")
    assert feed["items"][-1]["sender"] == "엄마" and "0:04" in feed["items"][-1]["text"]


def test_recorded_cheer_rejects_wrong_type_and_unknown_sender(base: str) -> None:
    from urllib.parse import quote

    status, _ = post_raw(f"{base}/api/family/cheer?sender={quote('엄마')}", b"<html>", "text/html")
    assert status == 400
    status, _ = post_raw(f"{base}/api/family/cheer?sender=x", b"voice", "audio/webm")
    assert status == 400
    assert inbox_types(base) == []


def test_unknown_audio_is_404(base: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(base + "/api/audio/nope", timeout=5)
    assert e.value.code == 404


def _calls_after(console: FakeConsole, pred: Any, tries: int = 300) -> list[tuple]:
    for _ in range(tries):
        if pred(console.calls):
            break
        threading.Event().wait(0.01)
    return console.calls


def test_manual_door_and_seat_reach_the_console() -> None:
    console = FakeConsole()
    gen = _serve(console)
    url = next(gen)
    assert post(url + "/api/manual/door_open")[0] == 200
    _calls_after(console, lambda c: ("door", "rear_left", True) in c)
    for _ in range(200):  # one-shot actions run on the runner thread; wait for it to finish before the next press
        if get(url + "/api/status")[1]["runner"]["state"] != "running":
            break
        threading.Event().wait(0.01)
    assert post(url + "/api/manual/seat_on")[0] == 200
    calls = _calls_after(console, lambda c: ("seat", "rear_left", True) in c)
    assert ("door", "rear_left", True) in calls and ("seat", "rear_left", True) in calls
    next(gen, None)


def test_manual_drive_keeps_going_until_park() -> None:
    console = FakeConsole()
    gen = _serve(console)
    url = next(gen)
    assert post(url + "/api/manual/drive")[0] == 200
    _calls_after(console, lambda c: any(x[0] == "controls" and x[1] >= 30 for x in c))
    status, data = post(url + "/api/manual/door_open")
    assert status == 409 and "주행" in data["error"]
    assert post(url + "/api/manual/park")[0] == 200
    calls = _calls_after(console, lambda c: c[-1:] == [("gear", "P")])
    assert ("gear", "D") in calls and calls[-1] == ("gear", "P")
    next(gen, None)


def test_unknown_manual_action_is_404(base: str) -> None:
    status, _ = post(base + "/api/manual/fly")
    assert status == 404


def _raw_request(base: str, path: str, headers: dict[str, str], body: bytes = b"") -> int:
    import http.client

    host, port = base.removeprefix("http://").split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=5)
    conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
    for k, v in headers.items():
        conn.putheader(k, v)
    conn.endheaders(body)
    status = conn.getresponse().status
    conn.close()
    return status


def test_requests_from_other_web_pages_are_refused(base: str) -> None:
    host = base.removeprefix("http://")
    # a page on another site can POST to localhost without a CORS preflight; Origin/Host give it away
    assert _raw_request(base, "/api/manual/drive", {"Host": host, "Origin": "https://evil.example"}) == 403
    assert _raw_request(base, "/api/manual/drive", {"Host": "evil.example:8090"}) == 403
    assert inbox_types(base) == []


def test_bad_content_length_is_rejected(base: str) -> None:
    host = base.removeprefix("http://")
    from urllib.parse import quote

    path = f"/api/family/cheer?sender={quote('엄마')}"
    for length in ("-1", "abc"):
        status = _raw_request(base, path, {"Host": host, "Content-Type": "audio/webm", "Content-Length": length})
        assert status == 400


def test_family_pickup_to_a_known_place_carries_its_coordinates(base: str) -> None:
    from scenario.scenarios import PLACES

    post(base + "/api/family/pickup", {"sender": "민지", "place": "○○수학학원 앞"})
    _, inbox = get(base + "/api/car/inbox?after=0")
    cmd = inbox["commands"][-1]
    assert (cmd["lat"], cmd["lon"]) == PLACES["○○수학학원 앞"]


def test_family_pickup_to_a_typed_place_has_no_coordinates(base: str) -> None:
    post(base + "/api/family/pickup", {"sender": "민지", "place": "편의점 앞"})
    _, inbox = get(base + "/api/car/inbox?after=0")
    assert "lat" not in inbox["commands"][-1]


def test_driver_voice_clip_is_served_from_the_voice_folder(tmp_path: Path) -> None:
    (tmp_path / "driver_yes.pcm").write_bytes(b"\x01\x02" * 10)
    for base in _serve(FakeConsole(), voice_dir=tmp_path):
        with urllib.request.urlopen(base + "/api/voice/driver_yes.pcm", timeout=5) as r:
            assert r.read() == b"\x01\x02" * 10
        for bad in ("driver_no.pcm", "..%2Fsecret.pcm", "driver_yes.wav"):
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + "/api/voice/" + bad, timeout=5)
            assert e.value.code == 404


def test_driver_voice_command_reaches_the_car(base: str) -> None:
    status, _ = post(base + "/api/driver/voice", {"clip": "driver_no"})
    assert status == 200
    _, inbox = get(base + "/api/car/inbox?after=0")
    cmd = inbox["commands"][-1]
    assert (cmd["type"], cmd["clip"], cmd["fallback_accept"]) == ("driver_voice", "driver_no", False)
    assert post(base + "/api/driver/voice", {"clip": "../x"})[0] == 400
