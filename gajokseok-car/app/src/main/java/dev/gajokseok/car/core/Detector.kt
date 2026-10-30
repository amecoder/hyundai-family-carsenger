package dev.gajokseok.car.core

// Pure decision engine for 가족석: vehicle signals + family commands in, effects out. No Android types here.

enum class GearState { PARK, DRIVE, REVERSE, NEUTRAL, UNKNOWN }
enum class Side { LEFT, RIGHT }
enum class Screen { HOME, DRIVING, PICKUP_PROMPT, CHEER }
enum class PickupPhase { NONE, REQUESTED, ACCEPTED, ARRIVED, BOARDED }

sealed interface Signal {
    data class Gear(val gear: GearState) : Signal
    data class Speed(val kph: Float) : Signal
    data class RearDoor(val side: Side, val open: Boolean) : Signal
    /** Seat occupancy with the real meaning (SDK inversion already corrected by the caller). */
    data class RearSeat(val side: Side, val occupied: Boolean) : Signal
    data class Battery(val socPct: Float) : Signal
}

sealed interface Command {
    data object Reset : Command
    data class SetTrip(val destination: String, val etaMin: Int, val driver: String, val child: String) : Command
    data class SetRestThreshold(val seconds: Int) : Command
    /** lat/lon = the place's coordinates when the family picked a known place; free-typed places have none. */
    data class PickupRequest(val by: String, val place: String, val etaMin: Int, val lat: Double? = null, val lon: Double? = null) : Command
    data class DriverReply(val accept: Boolean) : Command
    /** audioUrl = the family member's recorded clip; null means only the text is available (read by TTS). */
    data class Cheer(val from: String, val text: String, val audioUrl: String? = null, val durationMs: Long = 0) : Command
    /** Demo stand-in for the driver's voice: a clip fed to speech recognition; fallbackAccept applies if nothing is recognised. */
    data class DriverVoice(val clipUrl: String, val fallbackAccept: Boolean) : Command
}

sealed interface Effect {
    data class FamilyMessage(val text: String) : Effect
    data class Speak(val text: String) : Effect
    data class PlayCheer(val from: String, val text: String, val audioUrl: String? = null, val durationMs: Long = 0) : Effect
    data object StopVoice : Effect
    data class ShowScreen(val screen: Screen) : Effect
    data class Note(val text: String) : Effect
    data class Banner(val text: String?) : Effect
    /** Start listening for the driver's "응/아니" once the question has been spoken. */
    data object ListenForReply : Effect
    /** The question is settled (answered or timed out): close the microphone and drop any pending demo answer. */
    data object StopListening : Effect
    data class AddWaypoint(val place: String, val lat: Double, val lon: Double) : Effect
}

data class Trip(val destination: String, val etaMin: Int, val driver: String, val child: String)
data class Pickup(val by: String, val place: String, val etaMin: Int, val lat: Double? = null, val lon: Double? = null)

data class Snapshot(
    val gear: GearState,
    val speedKph: Float,
    val pickup: PickupPhase,
    val pickupPlace: String?,
    val pendingCheers: Int,
    val trip: Trip?,
    val drivingSinceMs: Long?,
    val socPct: Float?,
)

class Detector(
    private val maxCheersPerStop: Int = 3,
    private val chargeTargetPct: Float = 80f,
    /** question (~4 s) + the plan's 8 s without an answer */
    private val replyTimeoutMs: Long = 12_000,
) {
    private var gear = GearState.UNKNOWN
    private var speedKph = 0f
    private var trip: Trip? = null
    private var departures = 0
    private var phase = PickupPhase.NONE
    private var pickup: Pickup? = null
    private var pickupAskedAtMs: Long? = null
    private val pendingCheers = ArrayDeque<Command.Cheer>()
    private var drivingSinceMs: Long? = null
    private var restThresholdMs = 2 * 60 * 60 * 1000L
    private var restHintGiven = false
    private val doorOpen = mutableMapOf(Side.LEFT to false, Side.RIGHT to false)
    private val seatOccupied = mutableMapOf(Side.LEFT to false, Side.RIGHT to false)
    private val occupiedWhenDoorOpened = mutableMapOf(Side.LEFT to false, Side.RIGHT to false)
    private var socPct: Float? = null

    fun snapshot() = Snapshot(gear, speedKph, phase, pickup?.place, pendingCheers.size, trip, drivingSinceMs, socPct)

    fun onSignal(signal: Signal, nowMs: Long): List<Effect> = when (signal) {
        is Signal.Gear -> onGear(signal.gear, nowMs)
        is Signal.Speed -> { speedKph = signal.kph; emptyList() }
        is Signal.RearDoor -> onDoor(signal.side, signal.open)
        is Signal.RearSeat -> onSeat(signal.side, signal.occupied)
        is Signal.Battery -> onBattery(signal.socPct)
    }

    fun onCommand(command: Command, nowMs: Long): List<Effect> = when (command) {
        Command.Reset -> { resetAll(); listOf(Effect.StopVoice, Effect.Banner(null), Effect.ShowScreen(if (gear == GearState.DRIVE) Screen.DRIVING else Screen.HOME)) }
        is Command.SetTrip -> { trip = Trip(command.destination, command.etaMin, command.driver, command.child); emptyList() }
        is Command.SetRestThreshold -> { restThresholdMs = command.seconds * 1000L; emptyList() }
        is Command.PickupRequest -> onPickupRequest(command, nowMs)
        is Command.DriverReply -> onDriverReply(command.accept)
        is Command.Cheer -> onCheer(command)
        is Command.DriverVoice -> emptyList()
    }

    fun onTick(nowMs: Long): List<Effect> {
        val asked = pickupAskedAtMs
        if (phase == PickupPhase.REQUESTED && asked != null && nowMs - asked >= replyTimeoutMs) {
            return decline("답이 없어서 경유지를 추가하지 않았어요. 가족에게 전할게요.")
        }
        val since = drivingSinceMs ?: return emptyList()
        if (gear != GearState.DRIVE || restHintGiven || nowMs - since < restThresholdMs) return emptyList()
        restHintGiven = true
        val line = if (pendingCheers.isNotEmpty()) {
            "가족이 보낸 응원 메시지가 있어요. 쉬는 곳에 멈추면 들려 드릴게요."
        } else {
            "오래 운전하셨어요. 잠시 쉬어 가세요."
        }
        return listOf(Effect.Speak(line), Effect.Banner("연속 운전 ${restThresholdLabel()} · 쉬는 곳에 멈추면 응원을 들려 드려요"))
    }

    private fun restThresholdLabel(): String {
        val minutes = restThresholdMs / 60_000
        return if (minutes >= 60) "${minutes / 60}시간" else "${restThresholdMs / 1000}초(시연)"
    }

    private fun onGear(next: GearState, nowMs: Long): List<Effect> {
        val prev = gear
        gear = next
        if (next == prev) return emptyList()
        return when (next) {
            GearState.DRIVE -> onDepart(nowMs)
            GearState.PARK -> if (prev == GearState.UNKNOWN) emptyList() else onPark(nowMs)
            else -> emptyList()
        }
    }

    private fun onDepart(nowMs: Long): List<Effect> {
        val out = mutableListOf<Effect>(Effect.StopVoice, Effect.ShowScreen(Screen.DRIVING))
        drivingSinceMs = nowMs
        restHintGiven = false
        val t = trip
        if (t != null) {
            departures += 1
            when {
                phase == PickupPhase.BOARDED -> out += Effect.FamilyMessage("${t.child}와 함께 ${t.destination}으로 출발")
                departures == 1 -> out += Effect.FamilyMessage("${t.driver} 출발, ${t.etaMin}분 뒤 ${t.destination} 도착 예정")
            }
        }
        return out
    }

    private fun onPark(nowMs: Long): List<Effect> {
        val out = mutableListOf<Effect>(Effect.Banner(null))
        val drovelong = drivingSinceMs?.let { nowMs - it >= restThresholdMs } == true
        drivingSinceMs = null
        val t = trip
        when {
            phase == PickupPhase.ACCEPTED -> {
                phase = PickupPhase.ARRIVED
                out += Effect.FamilyMessage("${pickup?.place}에 도착했어요")
            }
            phase == PickupPhase.BOARDED && t != null -> {
                out += Effect.FamilyMessage("${t.destination}에 도착해서 주차했어요")
                phase = PickupPhase.NONE
                pickup = null
                trip = null
            }
            drovelong -> out += Effect.FamilyMessage("휴게소에서 쉬는 중이에요")
            t != null && departures > 0 && phase == PickupPhase.NONE -> {
                out += Effect.FamilyMessage("${t.destination}에 도착해서 주차했어요")
                trip = null
            }
        }
        out += playPendingCheers()
        if (out.none { it is Effect.ShowScreen }) out += Effect.ShowScreen(Screen.HOME)
        return out
    }

    private fun playPendingCheers(): List<Effect> {
        if (pendingCheers.isEmpty()) return emptyList()
        val out = mutableListOf<Effect>(Effect.ShowScreen(Screen.CHEER))
        repeat(minOf(maxCheersPerStop, pendingCheers.size)) {
            val c = pendingCheers.removeFirst()
            out += Effect.PlayCheer(c.from, c.text, c.audioUrl, c.durationMs)
        }
        return out
    }

    private fun onCheer(c: Command.Cheer): List<Effect> {
        pendingCheers.addLast(c)
        return if (gear == GearState.PARK) playPendingCheers() else listOf(Effect.Note("${c.from}의 응원 음성 도착 · 멈추면 재생"))
    }

    private fun onPickupRequest(c: Command.PickupRequest, nowMs: Long): List<Effect> {
        pickup = Pickup(c.by, c.place, c.etaMin, c.lat, c.lon)
        phase = PickupPhase.REQUESTED
        pickupAskedAtMs = nowMs
        return listOf(
            Effect.ShowScreen(Screen.PICKUP_PROMPT),
            Effect.Speak("${c.by}가 ${c.place}에서 픽업을 요청했어요. 경유지로 추가할까요?"),
            Effect.ListenForReply,
        )
    }

    private fun decline(spoken: String): List<Effect> {
        val back = Effect.ShowScreen(if (gear == GearState.DRIVE) Screen.DRIVING else Screen.HOME)
        phase = PickupPhase.NONE
        pickup = null
        pickupAskedAtMs = null
        return listOf(Effect.StopListening, back, Effect.Speak(spoken), Effect.FamilyMessage("지금은 들를 수 없어요. 조금만 기다려 줘"))
    }

    private fun onDriverReply(accept: Boolean): List<Effect> {
        val p = pickup
        if (phase != PickupPhase.REQUESTED || p == null) return emptyList()
        if (!accept) return decline("알겠어요. 가족에게 전할게요.")
        val back = Effect.ShowScreen(if (gear == GearState.DRIVE) Screen.DRIVING else Screen.HOME)
        phase = PickupPhase.ACCEPTED
        pickupAskedAtMs = null
        val driver = trip?.driver ?: "운전자"
        val out = mutableListOf(
            Effect.StopListening,
            back,
            Effect.Speak("${p.place}을 경유지로 추가했어요."),
            Effect.FamilyMessage("${driver}가 가는 중, ${p.etaMin}분 뒤 ${p.place} 도착"),
            Effect.Banner("경유지: ${p.place} · ${p.etaMin}분"),
        )
        if (p.lat != null && p.lon != null) out += Effect.AddWaypoint(p.place, p.lat, p.lon)
        return out
    }

    private fun onDoor(side: Side, open: Boolean): List<Effect> {
        val wasOpen = doorOpen.getValue(side)
        doorOpen[side] = open
        if (open && !wasOpen) {
            occupiedWhenDoorOpened[side] = seatOccupied.getValue(side)
            return emptyList()
        }
        if (open || !wasOpen || phase != PickupPhase.ARRIVED) return emptyList()
        // boarding = this side's seat became occupied during this door cycle (luggage leaves the seat empty)
        val boarded = seatOccupied.getValue(side) && !occupiedWhenDoorOpened.getValue(side)
        if (!boarded) return listOf(Effect.Note("${sideLabel(side)} 뒷문 개폐 · 착석 신호 없음 → 탑승 알림 보내지 않음"))
        phase = PickupPhase.BOARDED
        val child = pickup?.by ?: trip?.child ?: "가족"
        return listOf(Effect.FamilyMessage("뒷좌석 탑승 확인 ($child)"), Effect.Note("${sideLabel(side)} 뒷문 + ${sideLabel(side)} 뒷좌석 착석 → 탑승 확인"))
    }

    private fun onSeat(side: Side, occupied: Boolean): List<Effect> {
        seatOccupied[side] = occupied
        return emptyList()
    }

    private fun onBattery(pct: Float): List<Effect> {
        val prev = socPct
        socPct = pct
        return if (prev != null && prev < chargeTargetPct && pct >= chargeTargetPct) {
            listOf(Effect.FamilyMessage("충전 ${chargeTargetPct.toInt()}% 완료, 출발 가능"))
        } else {
            emptyList()
        }
    }

    private fun sideLabel(side: Side) = if (side == Side.LEFT) "왼쪽" else "오른쪽"

    private fun resetAll() {
        trip = null
        departures = 0
        phase = PickupPhase.NONE
        pickup = null
        pickupAskedAtMs = null
        pendingCheers.clear()
        drivingSinceMs = null
        restHintGiven = false
        restThresholdMs = 2 * 60 * 60 * 1000L
        Side.entries.forEach { doorOpen[it] = false; seatOccupied[it] = false; occupiedWhenDoorOpened[it] = false }
    }
}
