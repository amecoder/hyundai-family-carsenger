from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scenario.analytics import CORE_EVENTS, EVENTS, WEEK, EventStore, retention, week_of

# Monday 2026-11-02 00:00 KST as epoch seconds
MON = 1_793_545_200.0
DAY = 86_400.0


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def make_store(tmp_path: Path, clock: Clock | None = None) -> EventStore:
    return EventStore(tmp_path / "a.sqlite", tmp_path / "salt", clock=clock or Clock(MON))


def test_week_starts_monday_midnight_kst() -> None:
    assert week_of(MON) == week_of(MON + 7 * DAY - 1)
    assert week_of(MON - 1) == week_of(MON) - 1
    assert week_of(MON + 7 * DAY) == week_of(MON) + 1


def test_nothing_is_recorded_before_consent(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    assert store.record("demo", "엄마", "cheer_sent") is False
    assert store.count() == 0


def test_recorded_ids_are_pseudonymous(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.set_consent("demo", True)
    assert store.record("demo", "엄마", "cheer_sent") is True
    with sqlite3.connect(tmp_path / "a.sqlite") as db:
        dump = "\n".join(db.iterdump())
    assert "엄마" not in dump and "demo" not in dump
    assert "cheer_sent" in dump


def test_salt_lives_outside_the_database_and_is_reused(tmp_path: Path) -> None:
    make_store(tmp_path).set_consent("demo", True)
    salt = (tmp_path / "salt").read_bytes()
    assert len(salt) >= 32
    make_store(tmp_path)
    assert (tmp_path / "salt").read_bytes() == salt


def test_side_comes_from_the_event_catalog(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.set_consent("demo", True)
    store.record("demo", "차", "cheer_played")
    store.record("demo", "엄마", "cheer_sent")
    assert [r.side for r in store.rows()] == ["car", "family"]


def test_unknown_event_is_rejected(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.set_consent("demo", True)
    with pytest.raises(ValueError):
        store.record("demo", "엄마", "location_shared")


def test_withdrawing_consent_deletes_that_family_only(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.set_consent("demo", True)
    store.set_consent("other", True)
    store.record("demo", "엄마", "cheer_sent")
    store.record("other", "아빠", "cheer_sent")
    store.set_consent("demo", False)
    assert store.count() == 1
    assert store.consented("demo") is False
    assert store.record("demo", "엄마", "cheer_sent") is False


def test_events_survive_a_restart(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.set_consent("demo", True)
    store.record("demo", "차", "trip_arrived")
    again = make_store(tmp_path)
    assert again.count() == 1
    assert again.consented("demo") is True


def test_core_events_are_catalog_members() -> None:
    assert CORE_EVENTS <= set(EVENTS)


def _rows(tmp_path: Path, plan: list[tuple[str, str, float]]) -> EventStore:
    """plan: (family, event, ts)"""
    clock = Clock(MON)
    store = make_store(tmp_path, clock)
    for family in {f for f, _, _ in plan}:
        store.set_consent(family, True)
    for family, event, ts in plan:
        clock.now = ts
        store.record(family, "차" if EVENTS[event] == "car" else "엄마", event)
    return store


def test_retention_on_or_after_counts_a_later_return(tmp_path: Path) -> None:
    # A: weeks 0 and 2, B: week 0 only, C: weeks 0 and 1
    store = _rows(tmp_path, [
        ("A", "cheer_played", MON), ("A", "cheer_played", MON + 2 * WEEK),
        ("B", "cheer_played", MON + DAY),
        ("C", "pickup_accepted", MON + 2 * DAY), ("C", "cheer_played", MON + WEEK + DAY),
    ])
    out = retention(store.rows(), now=MON + 3 * WEEK, weeks=2)
    cohort = out["cohorts"][0]
    assert cohort["size"] == 3
    assert cohort["on_or_after"] == [1.0, 2 / 3, 1 / 3]
    assert cohort["on"] == [1.0, 1 / 3, 1 / 3]


def test_non_core_events_do_not_count_as_a_return(tmp_path: Path) -> None:
    store = _rows(tmp_path, [
        ("A", "cheer_played", MON),
        ("A", "family_room_opened", MON + WEEK),
    ])
    out = retention(store.rows(), now=MON + 2 * WEEK, weeks=1)
    assert out["cohorts"][0]["on_or_after"] == [1.0, 0.0]


def test_weeks_not_yet_finished_are_left_out(tmp_path: Path) -> None:
    store = _rows(tmp_path, [("A", "cheer_played", MON), ("A", "cheer_played", MON + WEEK)])
    out = retention(store.rows(), now=MON + WEEK + DAY, weeks=2)
    # week 1 is still running: not observable yet, so it is None rather than a guess
    assert out["cohorts"][0]["on_or_after"] == [1.0, None, None]


def test_cohorts_are_split_by_first_core_week(tmp_path: Path) -> None:
    store = _rows(tmp_path, [("A", "cheer_played", MON), ("B", "cheer_played", MON + WEEK)])
    out = retention(store.rows(), now=MON + 3 * WEEK, weeks=1)
    assert [c["size"] for c in out["cohorts"]] == [1, 1]
    assert out["cohorts"][1]["week_start"] == "2026-11-09"


def test_two_sided_weeks_need_both_car_and_family(tmp_path: Path) -> None:
    store = _rows(tmp_path, [
        ("A", "cheer_sent", MON), ("A", "cheer_played", MON + 60),
        ("B", "cheer_played", MON),
    ])
    out = retention(store.rows(), now=MON + WEEK, weeks=0)
    assert out["weekly"][0] == {"week_start": "2026-11-02", "active_families": 2, "two_sided_families": 1,
                                "core_families": 2}


def test_weekly_core_families_is_the_north_star(tmp_path: Path) -> None:
    # A only got an automatic boarding notice: active, but no two-way exchange happened
    store = _rows(tmp_path, [("A", "boarding_confirmed", MON), ("B", "pickup_accepted", MON)])
    out = retention(store.rows(), now=MON + WEEK, weeks=0)
    assert out["weekly"][0]["active_families"] == 2
    assert out["weekly"][0]["core_families"] == 1


def test_pickup_decline_ratio_is_reported_as_a_guardrail(tmp_path: Path) -> None:
    store = _rows(tmp_path, [
        ("A", "pickup_accepted", MON), ("A", "pickup_declined", MON + 60), ("A", "pickup_declined", MON + 120),
    ])
    out = retention(store.rows(), now=MON + WEEK, weeks=0)
    assert out["guardrails"] == {"pickup_answers": 3, "pickup_declined_ratio": 2 / 3, "pickup_timeouts": 0}


def test_scripted_demo_events_never_count_toward_retention(tmp_path: Path) -> None:
    clock = Clock(MON)
    store = make_store(tmp_path, clock)
    store.set_consent("A", True)
    store.record("A", "차", "cheer_played", source="scripted")
    clock.now = MON + WEEK
    store.record("A", "차", "cheer_played")
    assert [r.source for r in store.rows()] == ["scripted", "live"]
    out = retention(store.rows(), now=MON + 2 * WEEK, weeks=1)
    # only the live week-1 event exists, so the family starts in week 1, not week 0
    assert [c["week_start"] for c in out["cohorts"]] == ["2026-11-09"]
    assert out["scripted_events"] == 1


def test_unknown_source_is_rejected(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.set_consent("A", True)
    with pytest.raises(ValueError):
        store.record("A", "차", "cheer_played", source="guess")


def test_car_app_event_names_match_the_catalog() -> None:
    import re

    detector = Path(__file__).resolve().parents[2] / "gajokseok-car/app/src/main/java/dev/gajokseok/car/core/Detector.kt"
    names = set(re.findall(r'const val \w+ = "(\w+)"', detector.read_text()))
    assert names == {e for e, side in EVENTS.items() if side == "car"}


def test_consent_check_and_insert_are_one_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # a withdrawal landing between "is consent on?" and the insert must still leave nothing behind
    store = make_store(tmp_path)
    store.set_consent("A", True)
    store.set_consent("A", False)
    monkeypatch.setattr(store, "consented", lambda family: True)
    assert store.record("A", "차", "cheer_played") is False
    assert store.count() == 0


def test_running_cohort_is_marked_in_progress(tmp_path: Path) -> None:
    store = _rows(tmp_path, [("A", "cheer_played", MON), ("B", "cheer_played", MON + WEEK)])
    out = retention(store.rows(), now=MON + WEEK + DAY, weeks=1)
    assert [c["in_progress"] for c in out["cohorts"]] == [False, True]


def test_weeks_without_any_use_show_as_zero(tmp_path: Path) -> None:
    store = _rows(tmp_path, [("A", "cheer_played", MON), ("A", "cheer_played", MON + 2 * WEEK)])
    out = retention(store.rows(), now=MON + 3 * WEEK, weeks=0)
    assert [(w["week_start"], w["active_families"], w["core_families"]) for w in out["weekly"]] == [
        ("2026-11-02", 1, 1), ("2026-11-09", 0, 0), ("2026-11-16", 1, 1)]


def test_unanswered_pickups_are_counted_apart_from_declines(tmp_path: Path) -> None:
    store = _rows(tmp_path, [("A", "pickup_declined", MON), ("A", "pickup_timed_out", MON + 60),
                             ("A", "pickup_accepted", MON + 120)])
    out = retention(store.rows(), now=MON + WEEK, weeks=0)
    assert out["guardrails"] == {"pickup_answers": 2, "pickup_declined_ratio": 0.5, "pickup_timeouts": 1}


def test_a_half_written_salt_file_is_never_left_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os as os_mod

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os_mod, "link", boom)
    with pytest.raises(OSError):
        make_store(tmp_path)
    assert not (tmp_path / "salt").exists()
    monkeypatch.undo()
    make_store(tmp_path)
    assert len((tmp_path / "salt").read_bytes()) == 32


def test_a_lost_salt_with_existing_records_fails_closed(tmp_path: Path) -> None:
    # a new key would rename every family, so withdrawal could no longer find the old rows
    store = EventStore(tmp_path / "a.sqlite", tmp_path / "salt")
    store.set_consent("f", True)
    store.record("f", "엄마", "cheer_sent")
    store.close()
    (tmp_path / "salt").unlink()
    with pytest.raises(ValueError, match="키 파일"):
        EventStore(tmp_path / "a.sqlite", tmp_path / "salt")
    assert not (tmp_path / "salt").exists()


def test_withdrawn_events_leave_no_bytes_in_the_database_file(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "a.sqlite", tmp_path / "salt")
    store.set_consent("f", True)
    store.record("f", "엄마", "pickup_requested")
    store.set_consent("f", False)
    store.close()
    assert b"pickup_requested" not in (tmp_path / "a.sqlite").read_bytes()


def test_a_swapped_salt_is_refused(tmp_path: Path) -> None:
    # a different key of the right length would also rename every family: withdrawal would miss the old rows
    store = make_store(tmp_path)
    store.set_consent("f", True)
    store.close()
    (tmp_path / "salt").write_bytes(b"x" * 32)
    with pytest.raises(ValueError, match="다른 가명처리 키"):
        make_store(tmp_path)


def test_a_database_from_before_the_key_check_gets_one(tmp_path: Path) -> None:
    # the 11-02 pilot database has rows but no key check yet: its own key is trusted once and checked from then on
    store = make_store(tmp_path)
    store.set_consent("f", True)
    store.close()
    with sqlite3.connect(tmp_path / "a.sqlite") as db:
        db.execute("DELETE FROM meta")
    make_store(tmp_path).close()
    (tmp_path / "salt").write_bytes(b"y" * 32)
    with pytest.raises(ValueError, match="다른 가명처리 키"):
        make_store(tmp_path)


def test_withdrawal_keeps_the_deleted_rows_off_the_disk_journal(tmp_path: Path) -> None:
    # SQLite copies the pages it is about to change into a journal file first; for a withdrawal that copy would be the
    # very rows being deleted, so the journal stays in memory for that one transaction
    store = make_store(tmp_path)
    store.set_consent("f", True)
    store.record("f", "엄마", "pickup_requested")
    statements: list[str] = []
    store._db.set_trace_callback(statements.append)  # the journal mode is only visible on the connection
    store.set_consent("f", False)
    delete = next(i for i, s in enumerate(statements) if s.startswith("DELETE FROM events"))
    modes = [(i, s) for i, s in enumerate(statements) if "journal_mode" in s]
    assert any(i < delete and "MEMORY" in s for i, s in modes)
    assert any(i > delete and "DELETE" in s for i, s in modes)
    assert store._db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    store.close()


def test_a_lost_salt_without_any_record_starts_over(tmp_path: Path) -> None:
    # nothing to withdraw yet, so a lost key is not worth refusing to start: the new key becomes the checked one
    make_store(tmp_path).close()
    (tmp_path / "salt").unlink()
    store = make_store(tmp_path)
    store.set_consent("f", True)
    store.close()
    make_store(tmp_path).close()
