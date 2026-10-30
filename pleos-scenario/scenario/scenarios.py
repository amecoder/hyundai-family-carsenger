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
    """Command delivered to the car app (via the family hub inbox)."""

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


# demo places near Pangyo: the emulator navigation always starts at 수정구 시흥동 (127.0947, 37.4127)
PLACES: dict[str, tuple[float, float]] = {
    "○○수학학원 앞": (37.3947, 127.1112),
    "○○도서관 앞": (37.3825, 127.1189),
    "○○역 2번 출구": (37.4020, 127.1086),
    "○○태권도장 앞": (37.3998, 127.1150),
    "집": (37.3595, 127.1052),
}


def pickup_fields(by: str, place: str, eta_min: int) -> tuple[tuple[str, object], ...]:
    """pickup_request payload; known places get coordinates so the car can add a navigation waypoint."""
    fields: tuple[tuple[str, object], ...] = (("by", by), ("place", place), ("eta_min", eta_min))
    if place in PLACES:
        lat, lon = PLACES[place]
        fields += (("lat", lat), ("lon", lon))
    return fields


def pickup_request(by: str, place: str, eta_min: int) -> FamilySays:
    return FamilySays(by, f"아빠 나 끝났어! 데리러 와 · {place}", CarCommand("pickup_request", pickup_fields(by, place, eta_min)))


def cheer(sender: str, text: str, clip: str, label: str = "응원 음성") -> FamilySays:
    """A family voice message; clip names the recording in the voice folder (<clip>.wav) that the car plays."""
    return FamilySays(sender, f"🎙 {label} \"{text}\"", CarCommand("cheer", (("from", sender), ("text", text), ("clip", clip))))


def driver_says(accept: bool) -> CarCommand:
    """The driver answers out loud: the car runs a recorded answer through speech recognition."""
    return CarCommand("driver_voice", (("clip", "driver_yes" if accept else "driver_no"), ("fallback_accept", accept)))


@dataclass(frozen=True)
class Brake:
    """Slam on the brake: from_kph down to to_kph within the given seconds (the car app should call it harsh)."""

    from_kph: float
    to_kph: float
    seconds: float

    def run(self, v: Vehicle, sleep: Sleep, should_stop: ShouldStop) -> None:
        n = _ticks(self.seconds)
        for i in range(1, n + 1):
            if should_stop():
                return
            v.controls(self.from_kph + (self.to_kph - self.from_kph) * i / n, accelerator=0, brake=100)
            sleep(TICK_S)


Action = Gear | Door | Lock | Seat | Soc | Drive | Cruise | Stop | Wait | Brake | CarCommand | FamilySays


@dataclass(frozen=True)
class Step:
    title: str
    narration: str  # what is happening in the story
    expect: str  # what the car app should do at this moment
    actions: tuple[Action, ...] = ()


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    summary: str
    steps: tuple[Step, ...]


def reset(origin: str = "판교 회사", destination: str = "집", eta_min: int = 40, rest_seconds: int | None = None) -> Step:
    """Common opening: car parked with doors closed, rear seats empty, car app cleared and given today's trip."""
    actions: list[Action] = [
        Stop(0, 0.3), Gear("P"), Lock(False), Door("rear_left", False), Door("rear_right", False),
        Seat("rear_left", False), Seat("rear_right", False),
        CarCommand("reset"),
        CarCommand("set_trip", (("origin", origin), ("destination", destination), ("eta_min", eta_min),
                                ("driver", "아빠"), ("child", "민지"))),
    ]
    if rest_seconds is not None:
        actions.append(CarCommand("set_rest_threshold", (("seconds", rest_seconds),)))
    actions.append(Wait(2))
    return Step("준비: 주차 상태로 초기화", f"기어 P, 문 닫힘, 뒷좌석 비움, 오늘 경로: {origin} → {destination}", "가족방이 비워짐",
                tuple(actions))


ACADEMY = "○○수학학원 앞"
STT_NOTE = "(목소리는 공개 TTS 녹음을 마이크 대신 넣음)"

PICKUP = Scenario(
    "pickup",
    "평일 학원 픽업",
    "판교 회사에서 퇴근 → 민지의 픽업 요청 → 음성 승인 → 학원 도착 → 뒷좌석 탑승 확인 → 집으로 가는 길에 엄마 응원 (기능 ①②③)",
    (
        reset("판교 회사", "집", 40),
        Step("18:00 아빠 퇴근 출발", "기어 D, 시속 50km까지 가속", "엄마·민지 폰: \"아빠 판교 회사에서 출발, 40분 뒤 집 도착 예정\"",
             (Gear("D"), Drive(50, 4), Cruise(50, 2))),
        Step("18:15 민지가 「데리러 와」", "민지가 가족 웹에서 픽업 요청 (주행 유지)",
             "차 화면에 픽업 승인 카드 + 음성 질문 \"경유지로 추가할까요?\"",
             (pickup_request("민지", ACADEMY, 12), Cruise(50, 5))),
        Step("아빠가 \"응\"", f"운전자가 \"응, 추가해 줘\"라고 답함 → 음성 인식(STT)으로 승인 {STT_NOTE}",
             "경유지 추가 · 가족방: \"아빠가 가는 중, 12분 뒤 도착\"",
             (driver_says(True), Cruise(50, 4))),
        Step("18:27 학원 앞 도착", "감속해 정차, 기어 P", "가족방: \"○○수학학원 앞에 도착했어요\"",
             (Stop(50, 3), Gear("P"), Wait(2))),
        Step("18:28 민지 탑승", "왼쪽 뒷문 열림 → 왼쪽 뒷좌석 착석 → 문 닫힘", "엄마 폰: \"뒷좌석 탑승 확인 (민지)\"",
             (Door("rear_left", True), Wait(1.5), Seat("rear_left", True), Wait(1.5), Door("rear_left", False), Wait(2.5))),
        Step("집으로 출발 · 엄마가 응원 음성", "기어 D, 시속 40km. 주행 중 엄마가 응원 음성을 보냄",
             "가족방: \"민지와 함께 집으로 출발\" · 엄마 목소리가 주행 중 바로 재생",
             (Gear("D"), Drive(40, 3), Cruise(40, 1), cheer("엄마", "조심히 와~ 저녁 준비해 둘게", "cheer_mom"), Cruise(40, 5))),
        Step("18:55 집 도착", "정차 후 기어 P", "가족방: \"집에 도착해서 주차했어요\"",
             (Stop(40, 3), Gear("P"), Wait(3))),
    ),
)

LUGGAGE = Scenario(
    "luggage",
    "짐만 실음 (오탐 방지)",
    "동네 카페에서 태권도장으로 민지를 데리러 감 → 뒷문으로 가방만 실으면 알림이 가지 않고, 실제로 앉았을 때만 탑승 확인이 가는지 확인",
    (
        reset("동네 카페", "집", 15),
        Step("태권도장으로 가는 중 픽업 요청", "주행 중 민지의 요청 → 아빠 \"응\"", "경유지 추가",
             (Gear("D"), Drive(30, 3), pickup_request("민지", "○○태권도장 앞", 3), Cruise(30, 3), driver_says(True), Cruise(30, 2))),
        Step("태권도장 앞 정차", "기어 P", "가족방: \"○○태권도장 앞에 도착했어요\"", (Stop(30, 2), Gear("P"), Wait(2))),
        Step("오른쪽 뒷문으로 가방만 실음", "오른쪽 뒷문 열림 → 닫힘, 좌석은 비어 있음",
             "탑승 알림 보내지 않음 · 차 화면: \"착석 신호 없음\"",
             (Door("rear_right", True), Wait(2), Door("rear_right", False), Wait(3))),
        Step("민지가 왼쪽으로 실제 탑승", "왼쪽 뒷문 열림 → 착석 → 닫힘", "이때만 \"뒷좌석 탑승 확인 (민지)\"",
             (Door("rear_left", True), Wait(1.5), Seat("rear_left", True), Wait(1.5), Door("rear_left", False), Wait(3), Gear("P"))),
    ),
)

LONG_DRIVE = Scenario(
    "long_drive",
    "주말 장거리 · 할머니 댁",
    "집에서 전주 할머니 댁으로 → 고속도로에서 민지 응원이 바로 재생 → 2시간 연속 운전(시연용 20초)이면 휴식 권유 → 휴게소 정차 알림 (기능 ①③)",
    (
        reset("집", "전주 할머니 댁", 180, rest_seconds=20),
        Step("출발", "기어 D, 시속 100km까지 가속", "가족방: \"아빠 집에서 출발, 180분 뒤 전주 할머니 댁 도착 예정\"",
             (Gear("D"), Drive(100, 5))),
        Step("민지가 응원 음성을 보냄", "고속도로 주행 중 (2시간을 20초로 압축)", "민지 목소리가 주행 중 바로 재생",
             (Cruise(100, 2), cheer("민지", "아빠, 운전 오래 했지? 쉬었다 와요", "cheer_minji"), Cruise(100, 11))),
        Step("연속 운전 2시간 도달", "계속 주행", "차 음성 \"오래 운전하셨어요. 잠시 쉬어 가세요.\"",
             (Cruise(100, 7),)),
        Step("휴게소 정차", "감속해 정차, 기어 P", "가족방: \"휴게소에서 쉬는 중이에요\"",
             (Stop(100, 5), Gear("P"), Wait(4))),
        Step("다시 출발 후 도착", "기어 D로 주행 후 정차·P", "가족방: \"전주 할머니 댁에 도착해서 주차했어요\"",
             (Gear("D"), Drive(60, 3), Cruise(60, 3), Stop(60, 3), Gear("P"), Wait(3))),
    ),
)

SAFE_DRIVING = Scenario(
    "safe_driving",
    "급제동·과속 → 가족 응원",
    "혼자 퇴근하는 아빠가 과속 1번·급제동 1번을 하면 가족방에 안전 알림이 가고, 엄마의 빠른 답장 목소리가 주행 중인 차에서 바로 재생되는지 확인 (기능 ①④)",
    (
        reset("서울 본사", "집", 50),
        Step("퇴근길 출발", "기어 D, 시속 80km까지 가속", "가족방: \"아빠 서울 본사에서 출발, 50분 뒤 집 도착 예정\"",
             (Gear("D"), Drive(80, 4), Cruise(80, 2))),
        Step("고속도로에서 과속", "시속 125km로 11초 주행", "시속 110km를 넘긴 채 10초 → 과속 1번 (차 메모 \"과속 감지\")",
             (Drive(125, 3, from_kph=80), Cruise(125, 11))),
        Step("앞차 때문에 급제동", "시속 125km에서 1초 만에 시속 20km까지 급제동",
             "급제동 1번 → 합계 2번 → 가족방에 안전 알림 \"운전 중 급제동 1번, 과속 1번이 있었어요. 응원 한마디 보내 줄래요?\"",
             (Brake(125, 20, 0.9), Drive(60, 3, from_kph=20), Cruise(60, 3))),
        Step("엄마가 빠른 답장", "엄마가 안전 알림 아래 빠른 답장 버튼을 누름",
             "엄마 목소리 \"천천히 와도 돼. 안전이 제일이야\"가 주행 중인 차에서 바로 재생",
             (cheer("엄마", "천천히 와도 돼. 안전이 제일이야", "cheer_mom_slow", label="빠른 답장"), Cruise(60, 6))),
        Step("집 도착", "정차 후 기어 P", "가족방: \"집에 도착해서 주차했어요\"",
             (Stop(60, 3), Gear("P"), Wait(3))),
    ),
)

EV_CHARGE = Scenario(
    "ev_charge",
    "EV 충전 완료 알림",
    "아파트 충전소에 주차해 충전 중, 충전량이 목표(80%)에 도달하면 가족에게 알림 (기능 ①)",
    (
        reset("아파트 지하 충전소", "회사", 30),
        Step("충전 시작", "충전량 60%", "변화 없음", (Soc(60), Wait(2))),
        Step("충전 진행", "70% → 75%", "변화 없음", (Soc(70), Wait(2), Soc(75), Wait(2))),
        Step("목표 도달", "80%", "가족방: \"충전 80% 완료, 출발 가능\"", (Soc(80), Wait(3), Gear("P"))),
    ),
)

PICKUP_DECLINE = Scenario(
    "pickup_decline",
    "픽업 거절 (지금은 못 들름)",
    "분당 사무실에서 헬스장으로 가는 중 민지의 픽업 요청에 아빠가 \"아니\"라고 하면, 차는 경로를 바꾸지 않고 가족에게 거절 이유를 대신 전하는지 확인",
    (
        reset("분당 사무실", "헬스장", 25),
        Step("헬스장으로 출발", "기어 D, 시속 60km", "가족방: \"아빠 분당 사무실에서 출발, 25분 뒤 헬스장 도착 예정\"",
             (Gear("D"), Drive(60, 4), Cruise(60, 2))),
        Step("민지가 「데리러 와」", "주행 중 픽업 요청", "차 음성 질문 \"경유지로 추가할까요?\"",
             (pickup_request("민지", "○○역 2번 출구", 8), Cruise(60, 5))),
        Step("아빠가 \"아니\"", f"운전자가 \"아니, 지금은 안 돼\"라고 답함 → 음성 인식(STT)으로 거절 {STT_NOTE}",
             "차 음성 \"알겠어요. 가족에게 전할게요.\" · 가족방: \"지금은 들를 수 없어요. 조금만 기다려 줘\"",
             (driver_says(False), Cruise(60, 4))),
        Step("헬스장 도착", "정차 후 기어 P", "가족방: \"헬스장에 도착해서 주차했어요\" · 경유지 없음",
             (Stop(60, 3), Gear("P"), Wait(3))),
    ),
)

MANY_CHEERS = Scenario(
    "many_cheers",
    "응원이 연달아 온 날 (차례로 재생)",
    "집에서 마트로 가는 중 엄마·민지의 응원 4개가 연달아 와도 겹치지 않고 도착한 순서대로 하나씩 재생하는지 확인 (기능 ③)",
    (
        reset("집", "동네 마트", 10),
        Step("마트로 출발", "기어 D, 시속 40km", "가족방: \"아빠 집에서 출발, 10분 뒤 동네 마트 도착 예정\"",
             (Gear("D"), Drive(40, 3), Cruise(40, 1))),
        Step("응원 4개가 연달아 도착", "주행 중 엄마·민지가 번갈아 응원",
             "엄마 → 민지 → 엄마 → 민지 순서로 한 개씩 끝까지 재생 (겹치지 않음)",
             (cheer("엄마", "장 보느라 고생해", "cheer_mom_shop"), Cruise(40, 1),
              cheer("민지", "아빠, 아이스크림 사 와!", "cheer_minji_icecream"), Cruise(40, 1),
              cheer("엄마", "우유도 잊지 마", "cheer_mom_milk"), Cruise(40, 1),
              cheer("민지", "아빠 최고!", "cheer_minji_best"), Cruise(40, 9))),
        Step("마트 주차", "정차 후 기어 P", "가족방: \"동네 마트에 도착해서 주차했어요\"",
             (Stop(40, 3), Gear("P"), Wait(3))),
    ),
)

SOLO_LONG_DRIVE = Scenario(
    "solo_long_drive",
    "혼자 장거리 출장 (휴식 권유)",
    "판교 사무실에서 부산 출장지로 → 응원이 없어도 2시간 연속 운전(시연용 20초)이면 휴식을 권하고, 휴게소 정차를 가족에게 알리는지 확인",
    (
        reset("판교 사무실", "부산 출장지", 240, rest_seconds=20),
        Step("출발", "기어 D, 시속 100km", "가족방: \"아빠 판교 사무실에서 출발, 240분 뒤 부산 출장지 도착 예정\"",
             (Gear("D"), Drive(100, 5))),
        Step("계속 주행", "고속도로 주행 (2시간을 20초로 압축)", "변화 없음", (Cruise(100, 12),)),
        Step("연속 운전 2시간 도달", "계속 주행", "차 음성 \"오래 운전하셨어요. 잠시 쉬어 가세요.\"",
             (Cruise(100, 7),)),
        Step("휴게소 정차", "감속해 정차, 기어 P", "가족방: \"휴게소에서 쉬는 중이에요\"",
             (Stop(100, 5), Gear("P"), Wait(4))),
    ),
)

PARKED_PICKUP = Scenario(
    "parked_pickup",
    "출발 전 픽업 요청 · 오른쪽 탑승",
    "동네 마트 주차장에 있을 때 온 픽업 요청은 화면 카드로 보이고, 오른쪽 뒷문 탑승도 확인하며, 주차 중 응원은 카드와 함께 바로 재생하는지 확인",
    (
        reset("마트 주차장", "집", 30),
        Step("주차 중 민지의 「데리러 와」", "아빠는 아직 마트 주차장(P)", "차 화면에 픽업 카드가 그대로 보임 + 음성 질문",
             (pickup_request("민지", "○○도서관 앞", 10), Wait(4))),
        Step("아빠가 \"응\"", "주차 중 승인", "가족방: \"아빠가 가는 중, 10분 뒤 ○○도서관 앞 도착\"",
             (driver_says(True), Wait(3))),
        Step("도서관으로 출발", "기어 D, 시속 50km", "가족방: \"아빠 마트 주차장에서 출발, 30분 뒤 집 도착 예정\" · 경유지 배너",
             (Gear("D"), Drive(50, 4), Cruise(50, 3))),
        Step("도서관 앞 도착", "정차 후 기어 P", "가족방: \"○○도서관 앞에 도착했어요\"", (Stop(50, 3), Gear("P"), Wait(2))),
        Step("민지가 오른쪽으로 탑승", "오른쪽 뒷문 열림 → 오른쪽 뒷좌석 착석 → 닫힘", "가족방: \"뒷좌석 탑승 확인 (민지)\"",
             (Door("rear_right", True), Wait(1.5), Seat("rear_right", True), Wait(1.5), Door("rear_right", False), Wait(2.5))),
        Step("주차 중 엄마의 응원", "아직 주차(P) 중에 엄마가 응원을 보냄", "차 화면에 응원 카드 + 엄마 목소리 재생",
             (cheer("엄마", "민지 데리러 가 줘서 고마워", "cheer_mom_thanks"), Wait(6))),
        Step("집으로 출발 후 도착", "기어 D로 주행 후 정차·P", "가족방: \"민지와 함께 집으로 출발\" → \"집에 도착해서 주차했어요\"",
             (Gear("D"), Drive(40, 3), Cruise(40, 3), Stop(40, 3), Gear("P"), Wait(3))),
    ),
)

SCENARIOS: tuple[Scenario, ...] = (PICKUP, PARKED_PICKUP, PICKUP_DECLINE, LUGGAGE, LONG_DRIVE, SOLO_LONG_DRIVE,
                                   SAFE_DRIVING, MANY_CHEERS, EV_CHARGE)


def find(scenario_id: str) -> Scenario | None:
    return next((s for s in SCENARIOS if s.id == scenario_id), None)


# ---- manual controls: one-shot scenarios the presenter triggers by hand, mixed freely with the family web app ----

MANUAL_DRIVE_KPH = 40


def _manual(key: str, title: str, *actions: Action) -> Scenario:
    return Scenario(f"manual_{key}", f"수동 조작: {title}", "시연자가 직접 누른 조작", (Step(title, title, "", actions),))


MANUAL: dict[str, Scenario] = {
    "reset": Scenario("manual_reset", "수동 조작: 처음 상태로", "주차·문 닫힘·뒷좌석 비움, 가족방 비움", (reset("판교 회사", "집", 40),)),
    # cruises until the presenter presses park, which stops the runner (it brakes to 0 and shifts to P)
    "drive": _manual("drive", "출발", Gear("D"), Drive(MANUAL_DRIVE_KPH, 3), Cruise(MANUAL_DRIVE_KPH, 600)),
    "park": _manual("park", "정차", Stop(0, 0.3), Gear("P")),
    "door_open": _manual("door_open", "왼쪽 뒷문 열기", Door("rear_left", True)),
    "door_close": _manual("door_close", "왼쪽 뒷문 닫기", Door("rear_left", False)),
    "seat_on": _manual("seat_on", "왼쪽 뒷좌석 착석", Seat("rear_left", True)),
    "seat_off": _manual("seat_off", "왼쪽 뒷좌석 비움", Seat("rear_left", False)),
}
