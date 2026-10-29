from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

TICK_S = 0.3  # interval between speed updates while driving


class Vehicle(Protocol):
    def gear(self, letter: str) -> None: ...
    def door(self, area: str, opened: bool) -> None: ...
    def lock(self, locked: bool) -> None: ...
    def seat_occupied(self, area: str, occupied: bool) -> None: ...
    def soc(self, value: int) -> None: ...
    def controls(self, speed_kph: float, accelerator: float, brake: float) -> None: ...
    def keepalive(self, client_id: str) -> None: ...
    def car_command(self, type_: str, payload: dict) -> None: ...
    def family_says(self, sender: str, text: str) -> None: ...


Sleep = Callable[[float], None]
ShouldStop = Callable[[], bool]


def _ticks(seconds: float) -> int:
    return max(1, round(seconds / TICK_S))


@dataclass(frozen=True)
class Gear:
    value: str

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        v.gear(self.value)


@dataclass(frozen=True)
class Door:
    area: str
    opened: bool

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        v.door(self.area, self.opened)


@dataclass(frozen=True)
class Lock:
    locked: bool

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        v.lock(self.locked)


@dataclass(frozen=True)
class Seat:
    area: str
    occupied: bool

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        v.seat_occupied(self.area, self.occupied)


@dataclass(frozen=True)
class Soc:
    value: int

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        v.soc(self.value)


@dataclass(frozen=True)
class Drive:
    """Accelerate from from_kph to target_kph over the given seconds."""

    target_kph: float
    seconds: float
    from_kph: float = 0

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        n = _ticks(self.seconds)
        for i in range(1, n + 1):
            if should_stop():
                return
            v.controls(self.from_kph + (self.target_kph - self.from_kph) * i / n, accelerator=60, brake=0)
            sleep(TICK_S)


@dataclass(frozen=True)
class Cruise:
    """Hold a constant speed; re-sent every tick so the console never coasts down."""

    kph: float
    seconds: float

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        for _ in range(_ticks(self.seconds)):
            if should_stop():
                return
            v.controls(self.kph, accelerator=25, brake=0)
            sleep(TICK_S)


@dataclass(frozen=True)
class Stop:
    """Brake from from_kph down to a full stop."""

    from_kph: float
    seconds: float

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        n = _ticks(self.seconds)
        for i in range(1, n + 1):
            if should_stop():
                return
            v.controls(self.from_kph * (1 - i / n), accelerator=0, brake=100 if i == n else 70)
            sleep(TICK_S)


@dataclass(frozen=True)
class Wait:
    seconds: float

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        for _ in range(_ticks(self.seconds)):
            if should_stop():
                return
            sleep(TICK_S)


@dataclass(frozen=True)
class CarCommand:
    """Command delivered to the 가족석 car app (via the family hub inbox)."""

    type: str
    payload: tuple[tuple[str, object], ...] = ()

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        v.car_command(self.type, dict(self.payload))


@dataclass(frozen=True)
class FamilySays:
    """Something a family member does on the family web: shown in the family chat, optionally forwarded to the car."""

    sender: str
    text: str
    command: CarCommand | None = None

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        v.family_says(self.sender, self.text)
        if self.command:
            self.command.run(v, sleep, should_stop)


def pickup_request(by: str, place: str, eta_min: int) -> FamilySays:
    return FamilySays(by, f"아빠 나 끝났어! 데리러 와 · {place}",
                      CarCommand("pickup_request", (("by", by), ("place", place), ("eta_min", eta_min))))


def cheer(sender: str, text: str) -> FamilySays:
    return FamilySays(sender, f"🎙 응원 음성 \"{text}\"", CarCommand("cheer", (("from", sender), ("text", text))))


def driver_says(accept: bool) -> CarCommand:
    return CarCommand("driver_reply", (("accept", accept),))


Action = Gear | Door | Lock | Seat | Soc | Drive | Cruise | Stop | Wait | CarCommand | FamilySays


@dataclass(frozen=True)
class Step:
    title: str
    narration: str  # what is happening in the story
    expect: str  # what the 가족석 app should do at this moment
    actions: tuple[Action, ...] = ()


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    summary: str
    steps: tuple[Step, ...]


def reset(destination: str = "집", eta_min: int = 40, rest_seconds: int | None = None) -> Step:
    """Common opening: car parked with doors closed, rear seats empty, car app cleared and given today's trip."""
    actions: list[Action] = [
        Stop(0, 0.3), Gear("P"), Lock(False), Door("rear_left", False), Door("rear_right", False),
        Seat("rear_left", False), Seat("rear_right", False),
        CarCommand("reset"),
        CarCommand("set_trip", (("destination", destination), ("eta_min", eta_min), ("driver", "아빠"), ("child", "민지"))),
    ]
    if rest_seconds is not None:
        actions.append(CarCommand("set_rest_threshold", (("seconds", rest_seconds),)))
    actions.append(Wait(2))
    return Step("준비: 주차 상태로 초기화", f"기어 P, 문 닫힘, 뒷좌석 비움, 오늘 목적지: {destination}", "가족방이 비워짐", tuple(actions))


ACADEMY = "○○수학학원 앞"

PICKUP = Scenario(
    "pickup",
    "평일 학원 픽업",
    "출발 → 민지의 픽업 요청 → 음성 승인 → 학원 도착 → 뒷좌석 탑승 확인 → 집 도착·응원 재생 (기능 ①②③)",
    (
        reset(),
        Step("18:00 아빠 출발", "기어 D, 시속 50km까지 가속", "엄마·민지 폰: \"아빠 출발, 40분 뒤 집 도착 예정\"",
             (Gear("D"), Drive(50, 4), Cruise(50, 2))),
        Step("18:15 민지가 「데리러 와」", "민지가 가족 웹에서 픽업 요청 (주행 유지)",
             "차 화면에 픽업 승인 카드 + 음성 질문 \"경유지로 추가할까요?\"",
             (pickup_request("민지", ACADEMY, 12), Cruise(50, 5))),
        Step("아빠가 \"응\"", "운전자 음성 승인 (시연에서는 자동 응답)", "경유지 추가 · 가족방: \"아빠가 가는 중, 12분 뒤 도착\"",
             (driver_says(True), Cruise(50, 4))),
        Step("18:27 학원 앞 도착", "감속해 정차, 기어 P", "가족방: \"○○수학학원 앞에 도착했어요\"",
             (Stop(50, 3), Gear("P"), Wait(2))),
        Step("18:28 민지 탑승", "왼쪽 뒷문 열림 → 왼쪽 뒷좌석 착석 → 문 닫힘", "엄마 폰: \"뒷좌석 탑승 확인 (민지)\"",
             (Door("rear_left", True), Wait(1.5), Seat("rear_left", True), Wait(1.5), Door("rear_left", False), Wait(2.5))),
        Step("집으로 출발 · 엄마가 응원 음성", "기어 D, 시속 40km. 주행 중 엄마가 응원 음성을 보냄",
             "가족방: \"민지와 함께 집으로 출발\" · 응원은 주행 중이라 보관만 함",
             (Gear("D"), Drive(40, 3), Cruise(40, 1), cheer("엄마", "조심히 와~ 저녁 준비해 둘게"), Cruise(40, 4))),
        Step("18:55 집 도착", "정차 후 기어 P", "가족방: \"집에 도착해서 주차했어요\" + 엄마의 응원 음성 재생",
             (Stop(40, 3), Gear("P"), Wait(6))),
    ),
)

LUGGAGE = Scenario(
    "luggage",
    "짐만 실음 (오탐 방지)",
    "학원 앞에서 뒷문으로 가방만 실으면 알림이 가지 않고, 실제로 앉았을 때만 탑승 확인이 가는지 확인",
    (
        reset(destination="집", eta_min=15),
        Step("학원으로 가는 중 픽업 요청", "주행 중 민지의 요청 → 아빠 \"응\"", "경유지 추가",
             (Gear("D"), Drive(30, 3), pickup_request("민지", ACADEMY, 3), Cruise(30, 3), driver_says(True), Cruise(30, 2))),
        Step("학원 앞 정차", "기어 P", "가족방: \"○○수학학원 앞에 도착했어요\"", (Stop(30, 2), Gear("P"), Wait(2))),
        Step("오른쪽 뒷문으로 가방만 실음", "오른쪽 뒷문 열림 → 닫힘, 좌석은 비어 있음",
             "탑승 알림 보내지 않음 · 차 화면: \"착석 신호 없음\"",
             (Door("rear_right", True), Wait(2), Door("rear_right", False), Wait(3))),
        Step("민지가 왼쪽으로 실제 탑승", "왼쪽 뒷문 열림 → 착석 → 닫힘", "이때만 \"뒷좌석 탑승 확인 (민지)\"",
             (Door("rear_left", True), Wait(1.5), Seat("rear_left", True), Wait(1.5), Door("rear_left", False), Wait(3), Gear("P"))),
    ),
)

LONG_DRIVE = Scenario(
    "long_drive",
    "주말 장거리 · 휴게소 응원",
    "고속도로 주행 → 2시간 연속 운전(시연용 20초) → 휴게소 정차 시 민지의 응원 재생 (기능 ③)",
    (
        reset(destination="할머니 댁", eta_min=180, rest_seconds=20),
        Step("출발", "기어 D, 시속 100km까지 가속", "가족방: \"아빠 출발, 180분 뒤 할머니 댁 도착 예정\"",
             (Gear("D"), Drive(100, 5))),
        Step("민지가 응원 음성을 남김", "고속도로 주행 중 (2시간을 20초로 압축)", "주행 중이라 재생하지 않고 보관",
             (Cruise(100, 2), cheer("민지", "아빠 쉬었다 가세요"), Cruise(100, 11))),
        Step("연속 운전 2시간 도달", "계속 주행", "차 음성 한 문장: \"가족이 보낸 응원 메시지가 있어요. 쉬는 곳에 멈추면 들려 드릴게요.\"",
             (Cruise(100, 7),)),
        Step("휴게소 정차", "감속해 정차, 기어 P", "가족방: \"휴게소에서 쉬는 중이에요\" + 민지의 응원 재생",
             (Stop(100, 5), Gear("P"), Wait(7))),
        Step("다시 출발 후 도착", "기어 D로 주행 후 정차·P", "가족방: \"할머니 댁에 도착해서 주차했어요\"",
             (Gear("D"), Drive(60, 3), Cruise(60, 3), Stop(60, 3), Gear("P"), Wait(3))),
    ),
)

RED_LIGHT = Scenario(
    "red_light",
    "신호 대기 (재생 안 함 확인)",
    "속도가 0이어도 기어가 D면 응원 음성을 재생하지 않고, 주차(P)했을 때 재생하는지 확인",
    (
        reset(destination="집", eta_min=15),
        Step("시내 주행 · 엄마 응원 도착", "기어 D, 시속 40km. 엄마가 응원 음성을 보냄", "주행 중이라 보관",
             (Gear("D"), Drive(40, 3), cheer("엄마", "운전 조심해~"), Cruise(40, 2))),
        Step("빨간불 정지 (기어 D 유지)", "속도 0, 기어는 D", "응원 재생 안 함 · 화면도 주행 모드 유지",
             (Stop(40, 3), Wait(5))),
        Step("초록불 출발", "다시 시속 40km", "변화 없음", (Drive(40, 3), Cruise(40, 2))),
        Step("집 주차", "정차 후 기어 P", "가족방: \"집에 도착해서 주차했어요\" + 엄마의 응원 재생",
             (Stop(40, 3), Gear("P"), Wait(6))),
    ),
)

EV_CHARGE = Scenario(
    "ev_charge",
    "EV 충전 완료 알림",
    "주차 중 충전량이 목표(80%)에 도달하면 가족에게 알림 (기능 ①)",
    (
        reset(),
        Step("충전 시작", "충전량 60%", "변화 없음", (Soc(60), Wait(2))),
        Step("충전 진행", "70% → 75%", "변화 없음", (Soc(70), Wait(2), Soc(75), Wait(2))),
        Step("목표 도달", "80%", "가족방: \"충전 80% 완료, 출발 가능\"", (Soc(80), Wait(3), Gear("P"))),
    ),
)

PICKUP_DECLINE = Scenario(
    "pickup_decline",
    "픽업 거절 (지금은 못 들름)",
    "주행 중 민지의 픽업 요청에 아빠가 \"아니\"라고 하면, 차는 경로를 바꾸지 않고 가족에게 거절 이유를 대신 전하는지 확인",
    (
        reset(destination="집", eta_min=25),
        Step("퇴근길 출발", "기어 D, 시속 60km", "가족방: \"아빠 출발, 25분 뒤 집 도착 예정\"",
             (Gear("D"), Drive(60, 4), Cruise(60, 2))),
        Step("민지가 「데리러 와」", "주행 중 픽업 요청", "차 음성 질문 \"경유지로 추가할까요?\"",
             (pickup_request("민지", "○○역 2번 출구", 8), Cruise(60, 5))),
        Step("아빠가 \"아니\"", "운전자가 거절 (시연에서는 자동 응답)",
             "차 음성 \"알겠어요. 가족에게 전할게요.\" · 가족방: \"지금은 들를 수 없어요. 조금만 기다려 줘\"",
             (driver_says(False), Cruise(60, 4))),
        Step("집 도착", "정차 후 기어 P", "가족방: \"집에 도착해서 주차했어요\" · 경유지 없음",
             (Stop(60, 3), Gear("P"), Wait(3))),
    ),
)

MANY_CHEERS = Scenario(
    "many_cheers",
    "응원이 많은 날 (정차 1회당 3개)",
    "주행 중 응원이 4개 쌓이면 첫 정차에서 3개만 재생하고, 남은 1개는 다음 정차에서 재생하는지 확인",
    (
        reset(destination="마트", eta_min=10),
        Step("마트로 출발", "기어 D, 시속 40km", "가족방: \"아빠 출발, 10분 뒤 마트 도착 예정\"",
             (Gear("D"), Drive(40, 3), Cruise(40, 1))),
        Step("응원 4개가 연달아 도착", "주행 중 엄마·민지가 번갈아 응원", "모두 보관 · 홈 화면 \"도착하면 들을 응원 4개\"",
             (cheer("엄마", "장 보느라 고생해"), Cruise(40, 1), cheer("민지", "아이스크림 사 와!"), Cruise(40, 1),
              cheer("엄마", "우유도 잊지 마"), Cruise(40, 1), cheer("민지", "아빠 최고"), Cruise(40, 2))),
        Step("마트 주차", "정차 후 기어 P", "가족방: \"마트에 도착해서 주차했어요\" + 응원 3개만 차례로 재생, 1개는 다음 정차로",
             (Stop(40, 3), Gear("P"), Wait(16))),
        Step("집으로 출발 후 주차", "기어 D로 주행 후 정차·P", "남은 응원 1개(민지 \"아빠 최고\") 재생",
             (Gear("D"), Drive(40, 3), Cruise(40, 2), Stop(40, 3), Gear("P"), Wait(6))),
    ),
)

SOLO_LONG_DRIVE = Scenario(
    "solo_long_drive",
    "혼자 장거리 (휴식 권유)",
    "응원이 하나도 없어도 2시간 연속 운전(시연용 20초)이면 휴식을 권하고, 휴게소 정차를 가족에게 알리는지 확인",
    (
        reset(destination="부산", eta_min=240, rest_seconds=20),
        Step("출발", "기어 D, 시속 100km", "가족방: \"아빠 출발, 240분 뒤 부산 도착 예정\"", (Gear("D"), Drive(100, 5))),
        Step("응원 없이 계속 주행", "고속도로 주행 (2시간을 20초로 압축)", "변화 없음", (Cruise(100, 12),)),
        Step("연속 운전 2시간 도달", "계속 주행", "차 음성 \"오래 운전하셨어요. 잠시 쉬어 가세요.\" (보관된 응원이 없을 때의 문장)",
             (Cruise(100, 7),)),
        Step("휴게소 정차", "감속해 정차, 기어 P", "가족방: \"휴게소에서 쉬는 중이에요\" · 재생할 응원 없음",
             (Stop(100, 5), Gear("P"), Wait(4))),
    ),
)

PARKED_PICKUP = Scenario(
    "parked_pickup",
    "출발 전 픽업 요청 · 오른쪽 탑승",
    "주차 중에 온 픽업 요청은 화면 카드로 보이고, 오른쪽 뒷문 탑승도 확인하며, 주차 중 응원은 보관 없이 바로 재생하는지 확인",
    (
        reset(destination="집", eta_min=30),
        Step("주차 중 민지의 「데리러 와」", "아빠는 아직 주차 중(P)", "차 화면에 픽업 카드가 그대로 보임 + 음성 질문",
             (pickup_request("민지", "○○도서관 앞", 10), Wait(4))),
        Step("아빠가 \"응\"", "주차 중 승인", "가족방: \"아빠가 가는 중, 10분 뒤 ○○도서관 앞 도착\"",
             (driver_says(True), Wait(3))),
        Step("도서관으로 출발", "기어 D, 시속 50km", "가족방: \"아빠 출발, 30분 뒤 집 도착 예정\" · 경유지 배너",
             (Gear("D"), Drive(50, 4), Cruise(50, 3))),
        Step("도서관 앞 도착", "정차 후 기어 P", "가족방: \"○○도서관 앞에 도착했어요\"", (Stop(50, 3), Gear("P"), Wait(2))),
        Step("민지가 오른쪽으로 탑승", "오른쪽 뒷문 열림 → 오른쪽 뒷좌석 착석 → 닫힘", "가족방: \"뒷좌석 탑승 확인 (민지)\"",
             (Door("rear_right", True), Wait(1.5), Seat("rear_right", True), Wait(1.5), Door("rear_right", False), Wait(2.5))),
        Step("주차 중 엄마의 응원", "아직 주차(P) 중에 엄마가 응원을 보냄", "보관하지 않고 바로 재생",
             (cheer("엄마", "민지 데리러 가 줘서 고마워"), Wait(7))),
        Step("집으로 출발 후 도착", "기어 D로 주행 후 정차·P", "가족방: \"민지와 함께 집으로 출발\" → \"집에 도착해서 주차했어요\"",
             (Gear("D"), Drive(40, 3), Cruise(40, 3), Stop(40, 3), Gear("P"), Wait(3))),
    ),
)

SCENARIOS: tuple[Scenario, ...] = (PICKUP, PARKED_PICKUP, PICKUP_DECLINE, LUGGAGE, LONG_DRIVE, SOLO_LONG_DRIVE,
                                   RED_LIGHT, MANY_CHEERS, EV_CHARGE)


def find(scenario_id: str) -> Scenario | None:
    return next((s for s in SCENARIOS if s.id == scenario_id), None)


# ---- manual controls: one-shot scenarios the presenter triggers by hand, mixed freely with the family web app ----

MANUAL_DRIVE_KPH = 40


def _manual(key: str, title: str, *actions: Action) -> Scenario:
    return Scenario(f"manual_{key}", f"수동 조작: {title}", "시연자가 직접 누른 조작", (Step(title, title, "", actions),))


MANUAL: dict[str, Scenario] = {
    "reset": Scenario("manual_reset", "수동 조작: 처음 상태로", "주차·문 닫힘·뒷좌석 비움, 가족방 비움", (reset(),)),
    # cruises until the presenter presses park, which stops the runner (it brakes to 0 and shifts to P)
    "drive": _manual("drive", "출발", Gear("D"), Drive(MANUAL_DRIVE_KPH, 3), Cruise(MANUAL_DRIVE_KPH, 600)),
    "park": _manual("park", "정차", Stop(0, 0.3), Gear("P")),
    "door_open": _manual("door_open", "왼쪽 뒷문 열기", Door("rear_left", True)),
    "door_close": _manual("door_close", "왼쪽 뒷문 닫기", Door("rear_left", False)),
    "seat_on": _manual("seat_on", "왼쪽 뒷좌석 착석", Seat("rear_left", True)),
    "seat_off": _manual("seat_off", "왼쪽 뒷좌석 비움", Seat("rear_left", False)),
}
