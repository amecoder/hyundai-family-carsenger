from __future__ import annotations

import argparse
import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlparse

from scenario.family import FAMILY_SENDERS, MAX_AUDIO_BYTES, FamilyHub
from scenario.runner import ScenarioRunner
from scenario.scenarios import MANUAL, SCENARIOS, find
from scenario.screen import ScreenGrabber, adb_capture, default_adb, pillow_resize
from scenario.vc_client import VirtualConsoleClient

log = logging.getLogger(__name__)
STATIC = Path(__file__).resolve().parent.parent / "static"
INDEX = STATIC / "index.html"
FAMILY_PAGE = STATIC / "family.html"
MAX_BODY = 64 * 1024
MAX_FAMILY_TEXT = 300
MAX_PLACE = 40
PICKUP_ETA_MIN = 12  # demo stand-in for a navigation ETA
MAX_CLIP_MS = 60_000
# names this server may be reached by: this PC, and 10.0.2.2 = the PC as seen from inside the emulator
LOCAL_HOSTS = ("127.0.0.1", "localhost", "10.0.2.2")


class Console(Protocol):
    """The Virtual Console side: vehicle signal setters plus a state snapshot."""

    def gear(self, letter: str) -> None: ...
    def door(self, area: str, opened: bool) -> None: ...
    def lock(self, locked: bool) -> None: ...
    def seat_occupied(self, area: str, occupied: bool) -> None: ...
    def soc(self, value: int) -> None: ...
    def controls(self, speed_kph: float, accelerator: float, brake: float) -> None: ...
    def keepalive(self, client_id: str) -> None: ...
    def state(self) -> dict[str, Any]: ...


class DemoWorld:
    """What scenarios act on: the emulator (via Virtual Console) and the family hub (car app inbox + family chat)."""

    def __init__(self, console: Console, hub: FamilyHub) -> None:
        self.console = console
        self.hub = hub

    def gear(self, letter: str) -> None:
        self.console.gear(letter)

    def door(self, area: str, opened: bool) -> None:
        self.console.door(area, opened)

    def lock(self, locked: bool) -> None:
        self.console.lock(locked)

    def seat_occupied(self, area: str, occupied: bool) -> None:
        self.console.seat_occupied(area, occupied)

    def soc(self, value: int) -> None:
        self.console.soc(value)

    def controls(self, speed_kph: float, accelerator: float, brake: float) -> None:
        self.console.controls(speed_kph, accelerator, brake)

    def keepalive(self, client_id: str) -> None:
        self.console.keepalive(client_id)

    def car_command(self, type_: str, payload: dict) -> None:
        if type_ == "reset":
            self.hub.reset()
        self.hub.add_command(type_, **payload)

    def family_says(self, sender: str, text: str) -> None:
        self.hub.family_says(sender, text)


def _dig(data: Any, *keys: str) -> Any:
    # Virtual Console sends null sections until its bridge is ready, so treat None like a missing key
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def summarize(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "gear": _dig(state, "gear", "actual", "value"),
        "speed_kph": _dig(state, "controls", "speed_kph"),
        "door_rear_left": _dig(state, "body", "doors", "rear_left"),
        "door_rear_right": _dig(state, "body", "doors", "rear_right"),
        "seat_rear_left": _dig(state, "seat", "occupied", "rear_left"),
        "seat_rear_right": _dig(state, "seat", "occupied", "rear_right"),
        "doors_locked": _dig(state, "body", "door_locks", "all"),
        "soc": _dig(state, "ev_battery", "state_of_charge"),
    }


def scenario_payload() -> list[dict[str, Any]]:
    return [
        {"id": s.id, "title": s.title, "summary": s.summary,
         "steps": [{k: v for k, v in asdict(st).items() if k != "actions"} for st in s.steps]}
        for s in SCENARIOS
    ]


class ScenarioServer(ThreadingHTTPServer):
    def __init__(self, addr: tuple[str, int], console: Console, hub: FamilyHub, runner: ScenarioRunner,
                 grabber: ScreenGrabber | None) -> None:
        super().__init__(addr, Handler)
        self.console = console
        self.hub = hub
        self.runner = runner
        self.grabber = grabber


def _int_param(query: dict[str, list[str]], name: str) -> int:
    try:
        return int(query.get(name, ["0"])[0])
    except ValueError:
        return 0


def _clean_text(value: Any, limit: int) -> str | None:
    """Trimmed non-empty text within the limit, else None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if 0 < len(text) <= limit else None


def _clip_length(duration_ms: int) -> str:
    seconds = max(0, round(duration_ms / 1000))
    return f"{seconds // 60}:{seconds % 60:02d}"


class Handler(BaseHTTPRequestHandler):
    @property
    def app(self) -> ScenarioServer:
        return cast(ScenarioServer, self.server)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - name fixed by base class
        log.debug(format, *args)

    def _send(self, status: int, payload: Any, ctype: str = "application/json; charset=utf-8") -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _length(self) -> int | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        return length if length >= 0 else None

    def _trusted(self, post: bool) -> bool:
        """Refuse DNS-rebound hosts and, for POST, requests a page on another site sent to this local server."""
        port = self.app.server_address[1]
        allowed = {f"{h}:{port}" for h in LOCAL_HOSTS}
        if self.headers.get("Host") not in allowed:
            return False
        origin = self.headers.get("Origin")
        return not post or origin is None or origin in {f"http://{a}" for a in allowed}

    def _json_body(self) -> dict[str, Any] | None:
        length = self._length()
        if length is None or length <= 0 or length > MAX_BODY:
            return None
        try:
            data = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def do_GET(self) -> None:
        if not self._trusted(post=False):
            self._send(HTTPStatus.FORBIDDEN, {"error": "허용되지 않은 주소입니다"})
            return
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/":
            self._send(HTTPStatus.OK, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/scenarios":
            self._send(HTTPStatus.OK, scenario_payload())
        elif url.path == "/api/status":
            self._status()
        elif url.path == "/api/car/inbox":
            self._send(HTTPStatus.OK, self.app.hub.commands_after(_int_param(query, "after")))
        elif url.path == "/api/family/feed":
            self._send(HTTPStatus.OK, self.app.hub.feed_after(_int_param(query, "after")))
        elif url.path == "/api/screen":
            self._screen()
        elif url.path == "/family":
            self._send(HTTPStatus.OK, FAMILY_PAGE.read_bytes(), "text/html; charset=utf-8")
        elif url.path.startswith("/api/audio/"):
            self._audio(url.path.removeprefix("/api/audio/"))
        else:
            self._send(HTTPStatus.NOT_FOUND, {"error": "없는 경로입니다"})

    def _status(self) -> None:
        vehicle, error = None, None
        try:
            vehicle = summarize(self.app.console.state())
        except Exception as e:  # console down is a normal condition the UI must show, not a server error
            error = str(e)
        screen_error = self.app.grabber.error if self.app.grabber else "화면 캡처가 꺼져 있습니다"
        self._send(HTTPStatus.OK, {"runner": self.app.runner.status(), "vehicle": vehicle,
                                   "vehicle_error": error, "screen_error": screen_error})

    def _screen(self) -> None:
        image, ctype = self.app.grabber.latest() if self.app.grabber else (None, None)
        if image is None or ctype is None:
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "아직 화면이 없습니다"})
        else:
            self._send(HTTPStatus.OK, image, ctype)

    def _audio(self, clip_id: str) -> None:
        clip = self.app.hub.audio(clip_id)
        if clip is None:
            self._send(HTTPStatus.NOT_FOUND, {"error": "없는 녹음입니다"})
        else:
            self._send(HTTPStatus.OK, clip[0], clip[1])

    def do_POST(self) -> None:
        if not self._trusted(post=True):
            self._send(HTTPStatus.FORBIDDEN, {"error": "다른 사이트에서 온 요청은 받지 않습니다"})
            return
        url = urlparse(self.path)
        path = url.path
        if path == "/api/family/say":
            self._family_say()
        elif path == "/api/family/pickup":
            self._family_pickup()
        elif path == "/api/family/cheer":
            self._family_cheer(parse_qs(url.query))
        elif path.startswith("/api/manual/"):
            self._manual(path.removeprefix("/api/manual/"))
        elif path.startswith("/api/run/"):
            scenario = find(path.removeprefix("/api/run/"))
            if scenario is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "없는 시나리오입니다"})
            elif not self.app.runner.start(scenario):
                self._send(HTTPStatus.CONFLICT, {"error": "다른 시나리오가 실행 중입니다. 먼저 중지하세요"})
            else:
                self._send(HTTPStatus.OK, {"started": scenario.id})
        elif path == "/api/stop":
            self.app.runner.stop()
            self._send(HTTPStatus.OK, {"stopping": True})
        elif path == "/api/car/event":
            body = self._json_body()
            if not body or not isinstance(body.get("text"), str) or not isinstance(body.get("kind"), str):
                self._send(HTTPStatus.BAD_REQUEST, {"error": "kind와 text가 필요합니다"})
                return
            self.app.hub.car_event(body["kind"], body["text"][:500])
            self._send(HTTPStatus.OK, {"ok": True})
        else:
            self._send(HTTPStatus.NOT_FOUND, {"error": "없는 경로입니다"})

    def _family_say(self) -> None:
        # family chat text stays in the family room: reading messages aloud while driving was rejected in the plan
        body = self._json_body() or {}
        text = _clean_text(body.get("text"), MAX_FAMILY_TEXT)
        if body.get("sender") not in FAMILY_SENDERS or text is None:
            self._send(HTTPStatus.BAD_REQUEST, {"error": f"보내는 사람과 {MAX_FAMILY_TEXT}자 이하의 글이 필요합니다"})
            return
        self.app.hub.family_says(body["sender"], text)
        self._send(HTTPStatus.OK, {"ok": True})

    def _family_pickup(self) -> None:
        body = self._json_body() or {}
        place = _clean_text(body.get("place"), MAX_PLACE)
        sender = body.get("sender")
        if sender not in FAMILY_SENDERS or place is None:
            self._send(HTTPStatus.BAD_REQUEST, {"error": f"보내는 사람과 {MAX_PLACE}자 이하의 장소가 필요합니다"})
            return
        self.app.hub.family_says(sender, f"데리러 와 · {place}")
        self.app.hub.add_command("pickup_request", by=sender, place=place, eta_min=PICKUP_ETA_MIN)
        self._send(HTTPStatus.OK, {"ok": True})

    def _family_cheer(self, query: dict[str, list[str]]) -> None:
        # the body is the raw recording; who sent it and an optional caption ride in the query string
        sender = query.get("sender", [""])[0]
        caption = _clean_text(query.get("text", [""])[0], MAX_FAMILY_TEXT) or "응원 음성을 보냈어요"
        duration_ms = min(max(_int_param(query, "duration_ms"), 0), MAX_CLIP_MS)
        length = self._length()
        if length is None:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "Content-Length가 올바르지 않습니다"})
            return
        if sender not in FAMILY_SENDERS:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "보내는 사람이 올바르지 않습니다"})
            return
        if length > MAX_AUDIO_BYTES:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "녹음은 2MB 이하만 받을 수 있습니다"})
            return
        data = self.rfile.read(length)
        if len(data) != length:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "녹음이 끝까지 전송되지 않았습니다"})
            return
        try:
            clip_id = self.app.hub.add_audio(data, self.headers.get("Content-Type", ""))
        except ValueError as e:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(e)})
            return
        self.app.hub.family_says(sender, f"🎙 응원 음성 ({_clip_length(duration_ms)}) \"{caption}\"")
        self.app.hub.add_command("cheer", **{"from": sender, "text": caption, "audio_id": clip_id,
                                             "duration_ms": duration_ms})
        self._send(HTTPStatus.OK, {"audio_id": clip_id})

    def _manual(self, action: str) -> None:
        scenario = MANUAL.get(action)
        runner = self.app.runner
        if scenario is None:
            self._send(HTTPStatus.NOT_FOUND, {"error": "없는 수동 조작입니다"})
        elif action == "park" and runner.status()["state"] == "running":
            runner.stop()  # the runner brakes to 0 and shifts to P on its way out
            self._send(HTTPStatus.OK, {"parking": True})
        elif not runner.start(scenario):
            self._send(HTTPStatus.CONFLICT, {"error": "주행 중이거나 시나리오가 실행 중입니다. 먼저 정차하세요"})
        else:
            self._send(HTTPStatus.OK, {"started": scenario.id})


def make_server(console: Console, host: str = "127.0.0.1", port: int = 8090,
                sleep: Callable[[float], None] = time.sleep, hub: FamilyHub | None = None,
                grabber: ScreenGrabber | None = None) -> ScenarioServer:
    hub = hub or FamilyHub()
    runner = ScenarioRunner(DemoWorld(console, hub), sleep=sleep)
    return ScenarioServer((host, port), console, hub, runner, grabber)


def main() -> None:
    parser = argparse.ArgumentParser(description="가족석 시나리오 실행기 (Pleos Virtual Console 자동 조작 + 가족 서버 대역)")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--console", default="http://127.0.0.1:8088", help="Virtual Console 주소")
    parser.add_argument("--adb", default=default_adb(), help="에뮬레이터 화면 캡처에 쓸 adb 경로")
    parser.add_argument("--no-screen", action="store_true", help="에뮬레이터 화면 캡처를 끈다")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    grabber = None if args.no_screen else ScreenGrabber(adb_capture(args.adb), resize=pillow_resize())
    srv = make_server(VirtualConsoleClient(args.console), port=args.port, grabber=grabber)
    # 0.0.0.0 is not needed: the emulator reaches 127.0.0.1 through its 10.0.2.2 alias
    log.info("시나리오 실행기: http://127.0.0.1:%d (Virtual Console: %s)", args.port, args.console)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("종료합니다")
    finally:
        srv.runner.stop()
        if grabber:
            grabber.stop()
        srv.server_close()


if __name__ == "__main__":
    main()
