from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

# Demo stand-in for the family server: the car app posts events here and polls commands; the runner page reads the feed.

CAR_EVENT_KINDS = {"message", "speak", "note", "cheer_played", "cheer_skipped", "safety"}
FAMILY_SENDERS = ("엄마", "민지")
MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_AUDIO_CLIPS = 20
MAX_SOUNDS = 500


class FamilyHub:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
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
        # cheers sent but not yet played: (cheer_id, "sender: text" as the car reports it), oldest first
        self._waiting: list[tuple[int, str]] = []
        self._cheer_seq = 0
        # what the car made audible and when (epoch seconds), so a demo video can rebuild its sound track
        self._sounds: list[dict[str, Any]] = []
        self._served_clips: set[str] = set()
        # a pickup request the car has not answered yet; the car keeps only the latest one, so one flag is enough
        self._pickup_open = False

    def reset(self) -> None:
        with self._lock:
            self._commands = []
            self._feed = []
            self._waiting = []
            self._pickup_open = False
            self._cmd_reset_mark = self._cmd_seq
            self._feed_reset_mark = self._feed_seq

    def add_command(self, type_: str, **payload: Any) -> int:
        with self._lock:
            self._cmd_seq += 1
            self._commands = [*self._commands, {"seq": self._cmd_seq, "type": type_, **payload}]
            if type_ == "pickup_request":
                self._pickup_open = True
            return self._cmd_seq

    def answer_pickup(self) -> bool:
        """The car answered (accepted, declined or timed out): True only once per open request."""
        with self._lock:
            was_open, self._pickup_open = self._pickup_open, False
            return was_open

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

    def _append_feed_locked(self, kind: str, sender: str, text: str, **extra: Any) -> None:
        self._feed_seq += 1
        item = {"seq": self._feed_seq, "kind": kind, "sender": sender, "text": text, "at": time.strftime("%H:%M:%S"), **extra}
        self._feed = [*self._feed, item]

    def _append_feed(self, kind: str, sender: str, text: str) -> None:
        with self._lock:
            self._append_feed_locked(kind, sender, text)

    def _log_sound_locked(self, kind: str, **data: Any) -> None:
        self._sounds = [*self._sounds[-(MAX_SOUNDS - 1):], {"ts": self._clock(), "kind": kind, **data}]

    def car_event(self, kind: str, text: str) -> bool:
        """Posts the car's line to the family room. False only for a played cheer that matches no cheer the family sent."""
        if kind in {"cheer_played", "cheer_skipped"}:
            return self._cheer_settled(kind, text)
        with self._lock:
            if kind == "speak":
                self._log_sound_locked("speech", text=text)
            self._append_feed_locked(kind if kind in CAR_EVENT_KINDS else "note", "차", text)
        return True

    def _cheer_settled(self, kind: str, text: str) -> bool:
        """The car played a waiting cheer, or skipped it because the driver has cheers off: either way it leaves the queue."""
        with self._lock:
            match = next((w for w in self._waiting if w[1] == text), None)
            if match is None:
                self._append_feed_locked(kind, "차", text)
                return False
            self._waiting = [w for w in self._waiting if w is not match]
            self._append_feed_locked(kind, "차", text, cheer_id=match[0])
            return True

    def family_cheer(self, sender: str, feed_text: str, cheer_text: str, **payload: Any) -> int:
        """A family voice cheer: the chat bubble and the car command share one id, so the bubble can wait for playback."""
        with self._lock:
            self._cheer_seq += 1
            cheer_id = self._cheer_seq
            self._append_feed_locked("family", sender, feed_text, cheer_id=cheer_id)
            self._cmd_seq += 1
            self._commands = [*self._commands, {"seq": self._cmd_seq, "type": "cheer", "from": sender, "text": cheer_text,
                                                **payload}]
            self._waiting = [*self._waiting, (cheer_id, f"{sender}: {cheer_text}")]
            return cheer_id

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

    def audio_served(self, clip_id: str) -> None:
        """The car fetched a clip to play it; a player may fetch it again (range requests), which is not a new sound."""
        with self._lock:
            if clip_id not in self._served_clips:
                self._served_clips = {*self._served_clips, clip_id}
                self._log_sound_locked("clip", audio_id=clip_id)

    def sounds_since(self, since: float) -> list[dict[str, Any]]:
        with self._lock:
            return [s for s in self._sounds if s["ts"] >= since]
