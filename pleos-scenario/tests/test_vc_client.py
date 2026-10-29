from __future__ import annotations

import pytest

from scenario.vc_client import VirtualConsoleClient, VirtualConsoleError


class FakeTransport:
    def __init__(self, status: int = 200, body: bytes = b"{}") -> None:
        self.calls: list[tuple[str, str]] = []
        self.status = status
        self.body = body

    def __call__(self, method: str, url: str) -> tuple[int, bytes]:
        self.calls.append((method, url))
        return self.status, self.body


def make(status: int = 200, body: bytes = b"{}") -> tuple[VirtualConsoleClient, FakeTransport]:
    t = FakeTransport(status, body)
    return VirtualConsoleClient("http://vc:8088", transport=t), t


def test_gear_maps_letters_to_console_names() -> None:
    c, t = make()
    c.gear("D")
    c.gear("P")
    assert t.calls == [("PUT", "http://vc:8088/vehicle/gear?gear=Drive"), ("PUT", "http://vc:8088/vehicle/gear?gear=Park")]


def test_gear_rejects_unknown_letter() -> None:
    c, _ = make()
    with pytest.raises(ValueError):
        c.gear("X")


def test_door_uses_short_area_codes() -> None:
    c, t = make()
    c.door("rear_left", opened=True)
    c.door("rear_right", opened=False)
    assert t.calls == [("PUT", "http://vc:8088/vehicle/body?door_rl=true"), ("PUT", "http://vc:8088/vehicle/body?door_rr=false")]


def test_lock_and_seat_and_soc_urls() -> None:
    c, t = make()
    c.lock(False)
    c.seat_occupied("rear_left", True)
    c.soc(80)
    assert [u for _, u in t.calls] == [
        "http://vc:8088/vehicle/body?doors_locked=false",
        "http://vc:8088/vehicle/seat?kind=occupied&value=true&area=rear_left",
        "http://vc:8088/vehicle/ev-battery?field=soc&value=80",
    ]


def test_controls_clamps_values() -> None:
    c, t = make()
    c.controls(speed_kph=300, accelerator=-5, brake=150)
    assert t.calls[-1][1] == "http://vc:8088/vehicle/controls?speed=240&accelerator=0&brake=100"


def test_http_error_raises_readable_error() -> None:
    c, _ = make(status=500)
    with pytest.raises(VirtualConsoleError, match="500"):
        c.gear("P")


def test_state_parses_json() -> None:
    c, t = make(body=b'{"gear": {"actual": {"value": "Park"}}}')
    assert c.state()["gear"]["actual"]["value"] == "Park"
    assert t.calls == [("GET", "http://vc:8088/vehicle/state")]


def test_keepalive_posts_browser_session() -> None:
    c, t = make()
    c.keepalive("runner-1")
    assert t.calls == [("POST", "http://vc:8088/browser/session?client=runner-1")]
