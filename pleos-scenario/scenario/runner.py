from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from scenario.scenarios import TICK_S, Scenario, Vehicle

log = logging.getLogger(__name__)

PARK_BRAKE_KPH_PER_S = 20  # gentle enough that the car app does not count the stop as harsh braking


class _SpeedMemo:
    """Passes everything to the vehicle and remembers the last commanded speed, so a stop request can brake from it."""

    def __init__(self, vehicle: Vehicle) -> None:
        self._vehicle = vehicle
        self.last_kph = 0.0

    def controls(self, speed_kph: float, accelerator: float, brake: float) -> None:
        self._vehicle.controls(speed_kph, accelerator=accelerator, brake=brake)
        self.last_kph = speed_kph

    def __getattr__(self, name: str) -> Any:
        return getattr(self._vehicle, name)


class ScenarioRunner:
    """Runs one scenario at a time on a background thread; status() is safe to poll from the web server."""

    def __init__(self, vehicle: Vehicle, sleep: Callable[[float], None] = time.sleep, keepalive_interval: float = 1.0) -> None:
        self._vehicle = _SpeedMemo(vehicle)
        self._sleep = sleep
        self._keepalive_interval = keepalive_interval
        self._client_id = f"gajokseok-runner-{uuid.uuid4().hex[:8]}"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status: dict[str, Any] = {"state": "idle", "scenario": None, "step_index": -1, "log": [], "error": None}

    def start(self, scenario: Scenario) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop.clear()
            self._status = {"state": "running", "scenario": scenario.id, "step_index": -1, "log": [], "error": None}
            self._thread = threading.Thread(target=self._run, args=(scenario,), daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {**self._status, "log": list(self._status["log"])}

    def _update(self, **changes: Any) -> None:
        with self._lock:
            self._status = {**self._status, **changes}

    def _keepalive_loop(self, done: threading.Event) -> None:
        while not done.is_set():
            try:
                self._vehicle.keepalive(self._client_id)
            except Exception as e:  # a missed ping only matters if it repeats; the next action will surface the error
                log.warning("keepalive failed: %s", e)
            done.wait(self._keepalive_interval)

    def _run(self, scenario: Scenario) -> None:
        done = threading.Event()
        try:
            self._vehicle.keepalive(self._client_id)
            threading.Thread(target=self._keepalive_loop, args=(done,), daemon=True).start()
            for i, step in enumerate(scenario.steps):
                if self._stop.is_set():
                    break
                entry = {"title": step.title, "at": time.strftime("%H:%M:%S")}
                with self._lock:
                    self._status = {**self._status, "step_index": i, "log": [*self._status["log"], entry]}
                for action in step.actions:
                    if self._stop.is_set():
                        break
                    action.run(self._vehicle, self._sleep, self._stop.is_set)
            if self._stop.is_set():
                self._park_safely()
                self._update(state="stopped")
            else:
                self._update(state="done")
        except Exception as e:  # report any vehicle/HTTP failure to the UI instead of dying silently
            log.exception("scenario %s failed", scenario.id)
            self._update(state="failed", error=str(e))
        finally:
            done.set()

    def _park_safely(self) -> None:
        step = PARK_BRAKE_KPH_PER_S * TICK_S
        kph = self._vehicle.last_kph
        while kph > step:
            kph -= step
            self._vehicle.controls(kph, accelerator=0, brake=70)
            self._sleep(TICK_S)
        self._vehicle.controls(0, accelerator=0, brake=100)
        self._vehicle.gear("P")
