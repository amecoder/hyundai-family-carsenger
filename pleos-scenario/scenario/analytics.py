from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Usage events for retention: what happened and when, never where or what was said.
# No coordinates, places, message text or audio go in here, and ids are keyed hashes (pseudonymous data).

KST = timezone(timedelta(hours=9))
WEEK = 7 * 86_400.0
# epoch 0 is a Thursday; this is Monday 1970-01-05 00:00 KST
_FIRST_MONDAY = 4 * 86_400.0 - 9 * 3_600.0

# event name -> which side produces it
EVENTS: dict[str, str] = {
    # family side (family web)
    "family_room_opened": "family",
    "family_message_sent": "family",
    "pickup_requested": "family",
    "cheer_sent": "family",
    "quick_reply_sent": "family",
    # car side (in-car app)
    "trip_departed": "car",
    "trip_arrived": "car",
    "rest_stopped": "car",
    "rest_stop_accepted": "car",
    "pickup_accepted": "car",
    "pickup_declined": "car",
    "pickup_arrived": "car",
    "pickup_timed_out": "car",
    "boarding_confirmed": "car",
    "charge_completed": "car",
    "safety_alert_sent": "car",
    "cheer_played": "car",
}
# a two-way exchange between family and driver: a family voice played in the car, or a family pickup request the
# driver accepted. A family "came back" in a week only if one happened; weekly families with one = north star.
# Automatic notices (departure, arrival, boarding) are not exchanges, so they do not count.
CORE_EVENTS = frozenset({"cheer_played", "pickup_accepted"})
# live = a person used it (family web, presenter's manual controls, rehearsals);
# scripted = the car reported it while a demo scenario ran (or just after)
SOURCES = ("live", "scripted")


def week_of(ts: float) -> int:
    return int((ts - _FIRST_MONDAY) // WEEK)


def week_start(week: int) -> str:
    return datetime.fromtimestamp(_FIRST_MONDAY + week * WEEK, KST).date().isoformat()


@dataclass(frozen=True)
class Row:
    ts: float
    family: str
    actor: str
    side: str
    event: str
    source: str


def _load_salt(path: Path) -> bytes:
    """The hashing key is kept apart from the events, so the database alone cannot be traced back to people.
    It is written to a temporary file first and linked into place, so a crash never leaves a half-written key."""
    if path.exists():
        salt = path.read_bytes()
        if len(salt) < 32:
            raise ValueError(f"가명처리 키 파일이 손상됐습니다: {path}")
        return salt
    salt = secrets.token_bytes(32)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(salt)
        os.link(tmp, path)
    except FileExistsError:
        return _load_salt(path)  # another process created it first; use theirs
    finally:
        tmp.unlink(missing_ok=True)
    return salt


# fixed text whose keyed hash is kept in the database, so a swapped key is caught at start
KEY_CHECK = "key-check"


class EventStore:
    def __init__(self, db_path: Path, salt_path: Path, clock: Callable[[], float] = time.time) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute("PRAGMA secure_delete = ON")  # withdrawn rows are zeroed on disk, not just unlinked
        with self._db:
            self._db.execute("CREATE TABLE IF NOT EXISTS events (ts REAL NOT NULL, family TEXT NOT NULL,"
                             " actor TEXT NOT NULL, side TEXT NOT NULL, event TEXT NOT NULL, source TEXT NOT NULL)")
            self._db.execute("CREATE INDEX IF NOT EXISTS events_family ON events (family)")
            self._db.execute("CREATE TABLE IF NOT EXISTS consent (family TEXT PRIMARY KEY, granted INTEGER NOT NULL,"
                             " at REAL NOT NULL)")
            self._db.execute("CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
        if not salt_path.exists() and self._has_rows():
            self._db.close()
            raise ValueError(f"가명처리 키 파일이 없는데 기존 기록이 있습니다(새 키로는 철회 시 삭제가 안 됨): {salt_path}")
        self._salt = _load_salt(salt_path)
        self._check_key(salt_path)

    def _check_key(self, salt_path: Path) -> None:
        """A different key (a mixed-up backup, say) renames every family, so withdrawal would miss their rows: refuse it.
        A database without a check value yet (made before this check) trusts its current key once."""
        check = self._key(KEY_CHECK)
        try:
            with self._db:
                if not self._has_rows():
                    # nothing recorded yet, so nothing a new key could orphan (e.g. a lost key on an empty store)
                    self._db.execute("DELETE FROM meta WHERE name = 'key_check'")
                # OR IGNORE: two processes opening a fresh store at once both get here; the first value wins
                self._db.execute("INSERT OR IGNORE INTO meta VALUES ('key_check', ?)", (check,))
            stored = self._db.execute("SELECT value FROM meta WHERE name = 'key_check'").fetchone()[0]
        except sqlite3.Error:
            self._db.close()
            raise
        if not hmac.compare_digest(stored, check):
            self._db.close()
            raise ValueError(f"이 기록을 만든 키와 다른 가명처리 키입니다(철회 시 삭제가 안 됨): {salt_path}")

    def _has_rows(self) -> bool:
        return any(self._db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in ("events", "consent"))

    def _key(self, value: str) -> str:
        return hmac.new(self._salt, value.encode(), hashlib.sha256).hexdigest()[:24]

    def set_consent(self, family: str, granted: bool) -> None:
        """Withdrawing consent deletes everything already recorded for that family."""
        key = self._key(family)
        with self._lock:
            # the rollback journal would hold a copy of the very rows being deleted, so a withdrawal keeps it in memory;
            # ordinary writes keep the on-disk journal, which protects the database if the PC goes down mid-write
            # SQLite ignores the switch without an error inside an open transaction, so check that it took (fail closed)
            if not granted and self._db.execute("PRAGMA journal_mode = MEMORY").fetchone()[0] != "memory":
                raise sqlite3.OperationalError("철회 삭제용 메모리 저널로 바꾸지 못해 삭제를 멈췄습니다")
            try:
                with self._db:
                    self._db.execute("INSERT INTO consent VALUES (?, ?, ?) ON CONFLICT(family) DO UPDATE"
                                     " SET granted = excluded.granted, at = excluded.at", (key, int(granted), self._clock()))
                    if not granted:
                        self._db.execute("DELETE FROM events WHERE family = ?", (key,))
            finally:
                if not granted:
                    self._db.execute("PRAGMA journal_mode = DELETE")

    def consented(self, family: str) -> bool:
        with self._lock:
            row = self._db.execute("SELECT granted FROM consent WHERE family = ?", (self._key(family),)).fetchone()
        return bool(row and row[0])

    def record(self, family: str, actor: str, event: str, source: str = "live") -> bool:
        side = EVENTS.get(event)
        if side is None:
            raise ValueError(f"기록 목록에 없는 이벤트입니다: {event}")
        if source not in SOURCES:
            raise ValueError(f"출처는 {', '.join(SOURCES)} 중 하나여야 합니다: {source}")
        key = self._key(family)
        # consent check and insert are one statement, so a withdrawal cannot slip in between and leave a row behind
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO events SELECT ?, ?, ?, ?, ?, ? WHERE EXISTS"
                " (SELECT 1 FROM consent WHERE family = ? AND granted = 1)",
                (self._clock(), key, self._key(actor), side, event, source, key))
        return cur.rowcount == 1

    def count(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT count(*) FROM events").fetchone()[0])

    def rows(self) -> list[Row]:
        with self._lock:
            cur = self._db.execute("SELECT ts, family, actor, side, event, source FROM events ORDER BY ts, rowid")
            return [Row(*r) for r in cur.fetchall()]

    def close(self) -> None:
        with self._lock:
            self._db.close()


def _ratio(hits: int, size: int) -> float:
    return hits / size if size else 0.0


def retention(rows: Iterable[Row], now: float, weeks: int = 4) -> dict[str, Any]:
    """Weekly family cohorts. A family joins the cohort of its first week with a core event;
    week k counts it as back if a core event happened in exactly that week ("on")
    or in that week or any later one ("on_or_after"). Weeks not finished yet are None.
    Scripted demo events are counted apart and never enter a cohort."""
    rows = list(rows)
    scripted = sum(r.source != "live" for r in rows)
    rows = [r for r in rows if r.source == "live"]
    current = week_of(now)
    core_weeks: dict[str, set[int]] = defaultdict(set)
    sides: dict[tuple[int, str], set[str]] = defaultdict(set)
    answers = {"pickup_accepted": 0, "pickup_declined": 0, "pickup_timed_out": 0}
    for r in rows:
        w = week_of(r.ts)
        sides[(w, r.family)].add(r.side)
        if r.event in answers:
            answers[r.event] += 1
        if r.event in CORE_EVENTS:
            core_weeks[r.family].add(w)

    by_cohort: dict[int, list[set[int]]] = defaultdict(list)
    for active in core_weeks.values():
        by_cohort[min(active)].append(active)

    cohorts = []
    for start in sorted(by_cohort):
        members = by_cohort[start]
        size = len(members)
        on: list[float | None] = []
        after: list[float | None] = []
        for k in range(weeks + 1):
            target = start + k
            if k > 0 and target >= current:
                on.append(None)
                after.append(None)
                continue
            on.append(_ratio(sum(target in a for a in members), size))
            after.append(_ratio(sum(max(a) >= target for a in members), size))
        # a cohort whose week is still running can still grow, so its numbers are not final yet
        cohorts.append({"week_start": week_start(start), "size": size, "on": on, "on_or_after": after,
                        "in_progress": start >= current})

    # guardrail: the north star must not rise by pushing requests the driver keeps turning down.
    # An unanswered request is not a decline, so it is counted on its own.
    answered = answers["pickup_accepted"] + answers["pickup_declined"]
    guardrails = {"pickup_answers": answered, "pickup_declined_ratio": _ratio(answers["pickup_declined"], answered),
                  "pickup_timeouts": answers["pickup_timed_out"]}
    return {"cohorts": cohorts, "weekly": _weekly(sides, core_weeks, current), "core_events": sorted(CORE_EVENTS),
            "scripted_events": scripted, "guardrails": guardrails}


def _weekly(sides: dict[tuple[int, str], set[str]], core_weeks: dict[str, set[int]], current: int) -> list[dict[str, Any]]:
    """Every finished week from the first one seen, including weeks nobody used (shown as 0, not skipped)."""
    seen = [w for w, _ in sides if w < current]
    if not seen:
        return []
    weekly = []
    for w in range(min(seen), current):
        families = [s for (week, _), s in sides.items() if week == w]
        weekly.append({"week_start": week_start(w), "active_families": len(families),
                       "two_sided_families": sum({"car", "family"} <= s for s in families),
                       "core_families": sum(w in a for a in core_weeks.values())})
    return weekly
