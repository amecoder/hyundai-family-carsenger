from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

# Thin client for the Pleos Connect Virtual Console HTTP API (reverse-engineered from the console page, emulator v2.1.0).
Transport = Callable[[str, str], tuple[int, bytes]]

GEARS = {"P": "Park", "R": "Reverse", "N": "Neutral", "D": "Drive"}
DOOR_CODES = {"front_left": "fl", "front_right": "fr", "rear_left": "rl", "rear_right": "rr"}
SEAT_AREAS = ("driver", "passenger", "rear_left", "rear_right")
MAX_SPEED_KPH = 240


class VirtualConsoleError(RuntimeError):
    pass


def urllib_transport(method: str, url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        raise VirtualConsoleError(
            f"Virtual Console에 연결할 수 없습니다({url}). 에뮬레이터가 켜져 있고 "
            f"'adb forward tcp:8088 tcp:8088'을 실행했는지 확인하세요. 원인: {e.reason}"
        ) from e


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _clamp(value: float, low: float, high: float) -> int:
    return round(min(max(value, low), high))


class VirtualConsoleClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8088", transport: Transport = urllib_transport) -> None:
        self.base_url = base_url.rstrip("/")
        self._transport = transport

    def _call(self, method: str, path: str) -> bytes:
        url = f"{self.base_url}{path}"
        status, body = self._transport(method, url)
        if status >= 400:
            raise VirtualConsoleError(f"{method} {path} 실패: HTTP {status} {body[:200]!r}")
        return body

    def gear(self, letter: str) -> None:
        if letter not in GEARS:
            raise ValueError(f"unknown gear {letter!r}, expected one of {sorted(GEARS)}")
        self._call("PUT", f"/vehicle/gear?gear={GEARS[letter]}")

    def door(self, area: str, opened: bool) -> None:
        self._call("PUT", f"/vehicle/body?door_{DOOR_CODES[area]}={_flag(opened)}")

    def lock(self, locked: bool) -> None:
        self._call("PUT", f"/vehicle/body?doors_locked={_flag(locked)}")

    def seat_occupied(self, area: str, occupied: bool) -> None:
        if area not in SEAT_AREAS:
            raise ValueError(f"unknown seat area {area!r}")
        self._call("PUT", f"/vehicle/seat?kind=occupied&value={_flag(occupied)}&area={area}")

    def soc(self, value: int) -> None:
        self._call("PUT", f"/vehicle/ev-battery?field=soc&value={_clamp(value, 0, 100)}")

    def controls(self, speed_kph: float, accelerator: float, brake: float) -> None:
        self._call(
            "PUT",
            f"/vehicle/controls?speed={_clamp(speed_kph, 0, MAX_SPEED_KPH)}"
            f"&accelerator={_clamp(accelerator, 0, 100)}&brake={_clamp(brake, 0, 100)}",
        )

    def keepalive(self, client_id: str) -> None:
        # The console rejects /vehicle/controls with 503 emulator_inactive unless a browser session pinged within 3 s.
        self._call("POST", f"/browser/session?client={client_id}")

    def state(self) -> dict[str, Any]:
        return json.loads(self._call("GET", "/vehicle/state"))
