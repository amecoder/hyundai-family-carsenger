from __future__ import annotations

import threading

from scenario.runner import ScenarioRunner
from scenario.scenarios import PICKUP, SCENARIOS, CarCommand, Cruise, Drive, FamilySays, Gear, Scenario, Step, Stop, Wait


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def gear(self, g: str) -> None:
        self.calls.append(("gear", g))

    def door(self, area: str, opened: bool) -> None:
        self.calls.append(("door", area, opened))

    def lock(self, locked: bool) -> None:
        self.calls.append(("lock", locked))

    def seat_occupied(self, area: str, occupied: bool) -> None:
        self.calls.append(("seat", area, occupied))

    def soc(self, value: int) -> None:
        self.calls.append(("soc", value))

    def controls(self, speed_kph: float, accelerator: float, brake: float) -> None:
        self.calls.append(("controls", round(speed_kph), round(accelerator), round(brake)))

    def keepalive(self, client_id: str) -> None:
        self.keepalives = getattr(self, "keepalives", 0) + 1

    def car_command(self, type_: str, payload: dict) -> None:
        self.calls.append(("car", type_, tuple(sorted(payload.items()))))

    def family_says(self, sender: str, text: str) -> None:
        self.calls.append(("family", sender, text))


def no_sleep(_: float) -> None:
    return None


def run_sync(scenario: Scenario, client: RecordingClient) -> ScenarioRunner:
    r = ScenarioRunner(client, sleep=no_sleep)
    r.start(scenario)
    r.join(timeout=5)
    return r


def test_runs_steps_in_order_and_reports_done() -> None:
    sc = Scenario("t", "테스트", "설명", (Step("출발", "", "", (Gear("D"),)), Step("정차", "", "", (Gear("P"),))))
    client = RecordingClient()
    r = run_sync(sc, client)
    assert client.calls == [("gear", "D"), ("gear", "P")]
    st = r.status()
    assert st["state"] == "done"
    assert st["step_index"] == 1
    assert [e["title"] for e in st["log"]] == ["출발", "정차"]


def test_drive_ramps_speed_up_to_target() -> None:
    client = RecordingClient()
    Drive(60, seconds=3).run(client, no_sleep, lambda: False)
    speeds = [c[1] for c in client.calls]
    assert speeds[-1] == 60
    assert speeds == sorted(speeds)
    assert all(c[3] == 0 for c in client.calls)


def test_stop_ramps_down_to_zero_with_brake() -> None:
    client = RecordingClient()
    Stop(from_kph=50, seconds=2).run(client, no_sleep, lambda: False)
    assert client.calls[-1] == ("controls", 0, 0, 100)
    assert client.calls[0][1] < 50


def test_cruise_keeps_speed_constant() -> None:
    client = RecordingClient()
    Cruise(80, seconds=2).run(client, no_sleep, lambda: False)
    assert {c[1] for c in client.calls} == {80}


def test_stop_request_interrupts_and_parks_safely() -> None:
    gate = threading.Event()

    def blocking_sleep(_: float) -> None:
        gate.wait(0.01)

    sc = Scenario("t", "테스트", "", (Step("주행", "", "", (Gear("D"), Cruise(80, seconds=60))), Step("다음", "", "", (Wait(1),))))
    client = RecordingClient()
    r = ScenarioRunner(client, sleep=blocking_sleep)
    r.start(sc)
    r.stop()
    r.join(timeout=5)
    assert r.status()["state"] == "stopped"
    assert client.calls[-2:] == [("controls", 0, 0, 100), ("gear", "P")]


def test_stop_request_brakes_gently_so_the_car_does_not_report_harsh_braking() -> None:
    from scenario.scenarios import TICK_S

    sc = Scenario("t", "테스트", "", (Step("주행", "", "", (Gear("D"), Cruise(80, seconds=60))),))
    client = RecordingClient()
    r = ScenarioRunner(client, sleep=lambda _: threading.Event().wait(0.01))
    r.start(sc)
    threading.Event().wait(0.05)
    r.stop()
    r.join(timeout=10)
    speeds = [c[1] for c in client.calls if c[0] == "controls"]
    braking = speeds[speeds.index(80) + speeds.count(80):]
    assert braking[-1] == 0 and client.calls[-1] == ("gear", "P")
    drops = [a - b for a, b in zip([80, *braking], braking)]
    assert max(drops) <= 20 * TICK_S + 1  # at most ~20 km/h per second, below the car's harsh-braking threshold


def test_cannot_start_while_running() -> None:
    sc = Scenario("t", "테스트", "", (Step("주행", "", "", (Cruise(80, seconds=60),)),))
    r = ScenarioRunner(RecordingClient(), sleep=lambda _: threading.Event().wait(0.01))
    assert r.start(sc) is True
    assert r.start(sc) is False
    r.stop()
    r.join(timeout=5)


def test_client_error_marks_failed_with_message() -> None:
    class Broken(RecordingClient):
        def gear(self, g: str) -> None:
            raise RuntimeError("에뮬레이터 연결 실패")

    sc = Scenario("t", "테스트", "", (Step("출발", "", "", (Gear("D"),)),))
    r = run_sync(sc, Broken())
    st = r.status()
    assert st["state"] == "failed"
    assert "에뮬레이터 연결 실패" in st["error"]


def test_builtin_scenarios_are_well_formed() -> None:
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids)) >= 4
    for s in SCENARIOS:
        assert s.title and s.steps
        for step in s.steps:
            assert step.title
        # every scenario must end parked so the next one starts from a known state
        last_actions = [a for st in s.steps for a in st.actions if isinstance(a, Gear)]
        assert last_actions and last_actions[-1].value == "P", s.id


def test_builtin_scenarios_run_end_to_end_without_errors() -> None:
    for s in SCENARIOS:
        r = run_sync(s, RecordingClient())
        assert r.status()["state"] == "done", s.id


def test_keepalive_is_sent_while_running() -> None:
    sc = Scenario("t", "테스트", "", (Step("주행", "", "", (Gear("D"), Cruise(80, seconds=1))),))
    client = RecordingClient()
    r = ScenarioRunner(client, sleep=lambda _: threading.Event().wait(0.05), keepalive_interval=0.05)
    r.start(sc)
    r.join(timeout=5)
    assert r.status()["state"] == "done"
    assert getattr(client, "keepalives", 0) >= 2


def test_console_down_at_start_is_reported_as_failed() -> None:
    class Down(RecordingClient):
        def keepalive(self, client_id: str) -> None:
            raise RuntimeError("Virtual Console에 연결할 수 없습니다")

    sc = Scenario("t", "테스트", "", (Step("출발", "", "", (Gear("D"),)),))
    r = run_sync(sc, Down())
    assert r.status()["state"] == "failed"
    assert "연결할 수 없습니다" in r.status()["error"]


def test_family_and_car_actions_are_forwarded() -> None:
    sc = Scenario("t", "테스트", "", (Step("요청", "", "", (
        FamilySays("민지", "데리러 와", CarCommand("pickup_request", (("by", "민지"), ("eta_min", 12)))),
        CarCommand("driver_reply", (("accept", True),)),
    )),))
    client = RecordingClient()
    run_sync(sc, client)
    assert client.calls == [
        ("family", "민지", "데리러 와"),
        ("car", "pickup_request", (("by", "민지"), ("eta_min", 12))),
        ("car", "driver_reply", (("accept", True),)),
    ]


def test_pickup_scenario_drives_the_whole_family_flow() -> None:
    client = RecordingClient()
    run_sync(PICKUP, client)
    car = [c[1] for c in client.calls if c[0] == "car"]
    assert car[:2] == ["reset", "set_trip"]
    assert car.index("pickup_request") < car.index("driver_voice") < car.index("cheer")
    family = [c[1] for c in client.calls if c[0] == "family"]
    assert "민지" in family and "엄마" in family


def test_every_scenario_starts_by_resetting_the_car_app() -> None:
    for s in SCENARIOS:
        client = RecordingClient()
        run_sync(s, client)
        first_car = next(c for c in client.calls if c[0] == "car")
        assert first_car[1] == "reset", s.id


def _calls(scenario_id: str) -> list[tuple]:
    from scenario.scenarios import find

    sc = find(scenario_id)
    assert sc is not None, scenario_id
    client = RecordingClient()
    run_sync(sc, client)
    # skip the common reset step (it also parks and closes doors) so lookups see only the story
    start = next(i for i, c in enumerate(client.calls) if c[:2] == ("car", "set_trip"))
    return client.calls[start:]


def _index(calls: list[tuple], wanted: tuple) -> int:
    return next(i for i, c in enumerate(calls) if c[: len(wanted)] == wanted)


def test_pickup_decline_scenario_sends_a_refusal_while_driving() -> None:
    calls = _calls("pickup_decline")
    assert ("car", "driver_voice", (("clip", "driver_no"), ("fallback_accept", False))) in calls
    assert _index(calls, ("gear", "D")) < _index(calls, ("car", "driver_voice")) < _index(calls, ("gear", "P"))


def test_many_cheers_scenario_sends_four_cheers_while_driving() -> None:
    calls = _calls("many_cheers")
    cheers = [i for i, c in enumerate(calls) if c[:2] == ("car", "cheer")]
    drive, park = _index(calls, ("gear", "D")), _index(calls, ("gear", "P"))
    assert len(cheers) == 4 and all(drive < i < park for i in cheers)  # all arrive mid-drive and play right away


def test_solo_long_drive_has_rest_threshold_and_no_cheer() -> None:
    calls = _calls("solo_long_drive")
    assert any(c[:2] == ("car", "set_rest_threshold") for c in calls)
    assert not any(c[:2] == ("car", "cheer") for c in calls)
    # the car counts continuous driving from the shift to D, so accelerating ticks count too
    drive_ticks = sum(1 for c in calls if c[0] == "controls" and c[2] > 0)
    assert drive_ticks * 0.3 > 20  # drives past the 20 s demo threshold before stopping


def test_parked_pickup_scenario_requests_before_departure_and_boards_on_the_right() -> None:
    calls = _calls("parked_pickup")
    assert _index(calls, ("car", "pickup_request")) < _index(calls, ("gear", "D"))
    right = [_index(calls, ("door", "rear_right", True)), _index(calls, ("seat", "rear_right", True)),
             _index(calls, ("door", "rear_right", False))]
    assert right == sorted(right)
    # the cheer comes while still parked at the pickup spot, before the drive home
    cheer = _index(calls, ("car", "cheer"))
    assert right[-1] < cheer < next(i for i, c in enumerate(calls) if c == ("gear", "D") and i > right[-1])


def test_pickups_to_known_places_carry_coordinates_for_the_navigation() -> None:
    from scenario.scenarios import PLACES

    calls = _calls("pickup")
    pickup = next(c for c in calls if c[:2] == ("car", "pickup_request"))
    fields = dict(pickup[2])
    assert (fields["lat"], fields["lon"]) == PLACES[fields["place"]]


def _payload(call: tuple) -> dict:
    return dict(call[2])


def test_every_scenario_names_where_the_trip_starts_and_ends() -> None:
    trips = []
    for sc in SCENARIOS:
        client = RecordingClient()
        run_sync(sc, client)
        trips.append(_payload(next(c for c in client.calls if c[:2] == ("car", "set_trip"))))
    assert all(t["origin"] and t["destination"] for t in trips)
    assert len({t["destination"] for t in trips}) >= 6
    assert len({t["origin"] for t in trips}) >= 6


def test_every_scenario_cheer_brings_a_family_recording() -> None:
    for sc in SCENARIOS:
        client = RecordingClient()
        run_sync(sc, client)
        for c in client.calls:
            if c[:2] == ("car", "cheer"):
                assert _payload(c)["clip"].startswith("cheer_"), (sc.id, c)


def _max_braking_kph_per_s(calls: list[tuple]) -> float:
    from scenario.scenarios import TICK_S

    speeds = [c[1] for c in calls if c[0] == "controls"]
    k = 4  # compare speeds ~1.2 s apart, the way the car app measures braking over a 1 s window
    return max((speeds[i - k] - speeds[i]) / (k * TICK_S) for i in range(k, len(speeds))) if len(speeds) > k else 0


def test_only_the_safety_scenario_brakes_hard_enough_to_alert() -> None:
    for sc in SCENARIOS:
        client = RecordingClient()
        run_sync(sc, client)
        rate = _max_braking_kph_per_s(client.calls)
        if sc.id == "safe_driving":
            assert rate >= 30, rate
        else:
            assert rate < 30, (sc.id, rate)


def test_safety_scenario_speeds_for_ten_seconds_then_mom_answers_the_alert() -> None:
    from scenario.scenarios import TICK_S

    calls = _calls("safe_driving")
    over = [c for c in calls if c[0] == "controls" and c[1] > 110]
    assert len(over) * TICK_S >= 10
    hard_brake = max(i for i, c in enumerate(calls) if c[0] == "controls" and c[3] == 100 and c[1] > 0)
    reply = next(i for i, c in enumerate(calls) if c[:2] == ("car", "cheer"))
    assert hard_brake < reply < _index(calls, ("gear", "P"))
    assert _payload(calls[reply])["clip"] == "cheer_mom_slow"
