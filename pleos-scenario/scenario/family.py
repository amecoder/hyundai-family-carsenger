from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from typing import Any

# Demo stand-in for the family server: the car app posts events here and polls commands; the runner page reads the feed.

CAR_EVENT_KINDS = {"message", "speak", "note", "cheer_played"}
FAMILY_SENDERS = ("엄마", "민지")
MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_AUDIO_CLIPS = 20


class FamilyHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._commands: list[dict[str, Any]] = []
        self._feed: list[dict[str, Any]] = []
        self._cmd_seq = 0
        self._feed_seq = 0
        # sequences keep growing across resets; a cursor at or below the mark was handed out before the last reset
        self._cmd_reset_mark = 0
        self._feed_reset_mark = 0
        # recorded cheers live in memory only; the oldest clip is dropped once the store is full
        self._audio: OrderedDict[str, tuple[bytes, str]] = OrderedDict()

    def reset(self) -> None:
        with self._lock:
            self._commands = []
            self._feed = []
            self._cmd_reset_mark = self._cmd_seq
            self._feed_reset_mark = self._feed_seq

    def add_command(self, type_: str, **payload: Any) -> int:
        with self._lock:
            self._cmd_seq += 1
            self._commands = [*self._commands, {"seq": self._cmd_seq, "type": type_, **payload}]
            return self._cmd_seq

    def commands_after(self, after: int) -> dict[str, Any]:
        with self._lock:
            if after < 0:
                # a freshly started car app asks for "now" so it does not replay an old scenario
                return {"commands": [], "reset_cursor": False, "cursor": self._cmd_seq}
            # a cursor from before the last reset, or beyond our sequence (the server restarted), must start over
            stale = 0 < after <= self._cmd_reset_mark or after > self._cmd_seq
            start = 0 if stale else after
            return {"commands": [c for c in self._commands if c["seq"] > start], "reset_cursor": stale,
                    "cursor": self._cmd_seq}

    def _append_feed(self, kind: str, sender: str, text: str) -> None:
        with self._lock:
            self._feed_seq += 1
            item = {"seq": self._feed_seq, "kind": kind, "sender": sender, "text": text, "at": time.strftime("%H:%M:%S")}
            self._feed = [*self._feed, item]

    def car_event(self, kind: str, text: str) -> None:
        self._append_feed(kind if kind in CAR_EVENT_KINDS else "note", "차", text)

    def family_says(self, sender: str, text: str) -> None:
        self._append_feed("family", sender, text)

    def feed_after(self, after: int) -> dict[str, Any]:
        with self._lock:
            stale = 0 < after <= self._feed_reset_mark or after > self._feed_seq
            start = 0 if stale else after
            return {"items": [i for i in self._feed if i["seq"] > start], "reset": stale}

    def add_audio(self, data: bytes, mime: str) -> str:
        if not mime.startswith("audio/"):
            raise ValueError("음성 파일(audio/*)만 받을 수 있습니다")
        if not data:
            raise ValueError("녹음이 비어 있습니다")
        if len(data) > MAX_AUDIO_BYTES:
            raise ValueError("녹음은 2MB 이하만 받을 수 있습니다")
        clip_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._audio[clip_id] = (data, mime)
            while len(self._audio) > MAX_AUDIO_CLIPS:
                self._audio.popitem(last=False)
        return clip_id

    def audio(self, clip_id: str) -> tuple[bytes, str] | None:
        with self._lock:
            return self._audio.get(clip_id)
