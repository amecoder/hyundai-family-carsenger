from __future__ import annotations

import threading

from scenario.screen import ScreenGrabber


def test_grabber_captures_lazily_and_stops_when_idle() -> None:
    calls = []
    done = threading.Event()

    def capture() -> bytes:
        calls.append(1)
        if len(calls) >= 2:
            done.set()
        return b"\x89PNG-fake"

    g = ScreenGrabber(capture, interval=0.01, idle_timeout=0.2, resize=None)
    assert calls == []
    first = g.latest()  # first request starts the loop
    assert done.wait(2)
    image, ctype = g.latest()
    assert image == b"\x89PNG-fake"
    assert ctype == "image/png"
    assert first == (None, None) or first[0] == b"\x89PNG-fake"
    g.stop()


def test_capture_failure_is_reported_not_raised() -> None:
    def capture() -> bytes:
        raise RuntimeError("adb 없음")

    g = ScreenGrabber(capture, interval=0.01, idle_timeout=0.2, resize=None)
    g.latest()
    for _ in range(100):
        if g.error:
            break
        threading.Event().wait(0.01)
    assert "adb 없음" in (g.error or "")
    g.stop()
