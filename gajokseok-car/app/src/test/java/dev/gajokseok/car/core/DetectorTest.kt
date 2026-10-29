package dev.gajokseok.car.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class DetectorTest {
    private lateinit var d: Detector
    private var now = 0L

    private fun sig(s: Signal): List<Effect> = d.onSignal(s, now)
    private fun cmd(c: Command): List<Effect> = d.onCommand(c, now)
    private fun messages(effects: List<Effect>) = effects.filterIsInstance<Effect.FamilyMessage>().map { it.text }

    @Before
    fun setUp() {
        d = Detector()
        now = 0L
        cmd(Command.SetTrip(destination = "집", etaMin = 40, driver = "아빠", child = "민지"))
        sig(Signal.Gear(GearState.PARK))
    }

    private fun drive(): List<Effect> = sig(Signal.Gear(GearState.DRIVE))
    private fun park(): List<Effect> = sig(Signal.Gear(GearState.PARK))

    private fun acceptPickup() {
        cmd(Command.PickupRequest(by = "민지", place = "○○수학학원 앞", etaMin = 12))
        cmd(Command.DriverReply(accept = true))
    }

    private fun board(side: Side = Side.LEFT): List<Effect> =
        sig(Signal.RearDoor(side, open = true)) + sig(Signal.RearSeat(side, occupied = true)) + sig(Signal.RearDoor(side, open = false))

    @Test
    fun departureSendsEtaMessageAndShowsDrivingScreen() {
        val e = drive()
        assertEquals(listOf("아빠 출발, 40분 뒤 집 도착 예정"), messages(e))
        assertTrue(Effect.ShowScreen(Screen.DRIVING) in e)
    }

    @Test
    fun pickupRequestWhileDrivingAsksDriverByVoice() {
        drive()
        val e = cmd(Command.PickupRequest(by = "민지", place = "○○수학학원 앞", etaMin = 12))
        assertTrue(e.any { it is Effect.Speak && it.text.contains("민지가 ○○수학학원 앞에서 픽업을 요청했어요") })
        assertTrue(Effect.ShowScreen(Screen.PICKUP_PROMPT) in e)
        assertEquals(PickupPhase.REQUESTED, d.snapshot().pickup)
    }

    @Test
    fun acceptingPickupTellsFamilyTheEta() {
        drive()
        cmd(Command.PickupRequest(by = "민지", place = "○○수학학원 앞", etaMin = 12))
        val e = cmd(Command.DriverReply(accept = true))
        assertEquals(listOf("아빠가 가는 중, 12분 뒤 ○○수학학원 앞 도착"), messages(e))
        assertTrue(Effect.ShowScreen(Screen.DRIVING) in e)
        assertEquals(PickupPhase.ACCEPTED, d.snapshot().pickup)
    }

    @Test
    fun decliningPickupTellsFamily() {
        drive()
        cmd(Command.PickupRequest(by = "민지", place = "○○수학학원 앞", etaMin = 12))
        val e = cmd(Command.DriverReply(accept = false))
        assertEquals(listOf("지금은 들를 수 없어요. 조금만 기다려 줘"), messages(e))
        assertEquals(PickupPhase.NONE, d.snapshot().pickup)
    }

    @Test
    fun parkingAtPickupPlaceAnnouncesArrival() {
        drive()
        acceptPickup()
        val e = park()
        assertEquals(listOf("○○수학학원 앞에 도착했어요"), messages(e))
        assertEquals(PickupPhase.ARRIVED, d.snapshot().pickup)
    }

    @Test
    fun doorPlusSeatAtPickupConfirmsBoarding() {
        drive(); acceptPickup(); park()
        val e = board()
        assertEquals(listOf("뒷좌석 탑승 확인 (민지)"), messages(e))
        assertEquals(PickupPhase.BOARDED, d.snapshot().pickup)
    }

    @Test
    fun doorWithoutSeatIsNotBoarding() {
        drive(); acceptPickup(); park()
        val e = sig(Signal.RearDoor(Side.RIGHT, open = true)) + sig(Signal.RearDoor(Side.RIGHT, open = false))
        assertTrue(messages(e).isEmpty())
        assertTrue(e.any { it is Effect.Note && it.text.contains("착석 신호 없음") })
        assertEquals(PickupPhase.ARRIVED, d.snapshot().pickup)
    }

    @Test
    fun seatOnOtherSideDoesNotCount() {
        drive(); acceptPickup(); park()
        val e = sig(Signal.RearDoor(Side.RIGHT, open = true)) + sig(Signal.RearSeat(Side.LEFT, occupied = true)) +
            sig(Signal.RearDoor(Side.RIGHT, open = false))
        assertTrue(messages(e).isEmpty())
    }

    @Test
    fun cheerWhileDrivingIsHeldUntilParked() {
        drive()
        val held = cmd(Command.Cheer(from = "엄마", text = "조심히 와~"))
        assertFalse(held.any { it is Effect.PlayCheer })
        assertEquals(1, d.snapshot().pendingCheers)
        val e = park()
        assertTrue(Effect.PlayCheer("엄마", "조심히 와~") in e)
        assertEquals(0, d.snapshot().pendingCheers)
    }

    @Test
    fun cheerWhileParkedPlaysImmediately() {
        val e = cmd(Command.Cheer(from = "엄마", text = "잘 다녀와"))
        assertTrue(Effect.PlayCheer("엄마", "잘 다녀와") in e)
    }

    @Test
    fun recordedCheerKeepsItsClipThroughTheDriveAndPlaysItOnPark() {
        drive()
        val url = "http://10.0.2.2:8090/api/audio/abc123"
        val held = cmd(Command.Cheer(from = "엄마", text = "조심히 와", audioUrl = url, durationMs = 4200))
        assertFalse(held.any { it is Effect.PlayCheer })
        val e = park()
        assertTrue(Effect.PlayCheer("엄마", "조심히 와", audioUrl = url, durationMs = 4200) in e)
    }

    @Test
    fun atMostThreeCheersPerStop() {
        drive()
        repeat(4) { cmd(Command.Cheer(from = "엄마", text = "응원 $it")) }
        val played = park().filterIsInstance<Effect.PlayCheer>()
        assertEquals(3, played.size)
        assertEquals(1, d.snapshot().pendingCheers)
    }

    @Test
    fun homeArrivalAfterBoardingAnnouncesParkingAndPlaysCheer() {
        drive(); acceptPickup(); park(); board()
        drive()
        cmd(Command.Cheer(from = "엄마", text = "조심히 와~"))
        val e = park()
        assertEquals(listOf("집에 도착해서 주차했어요"), messages(e))
        assertTrue(Effect.PlayCheer("엄마", "조심히 와~") in e)
        assertTrue(Effect.ShowScreen(Screen.CHEER) in e)
    }

    @Test
    fun secondDepartureWithChildAboardMentionsChild() {
        drive(); acceptPickup(); park(); board()
        val e = drive()
        assertEquals(listOf("민지와 함께 집으로 출발"), messages(e))
    }

    @Test
    fun redLightStopInDriveDoesNothing() {
        drive()
        cmd(Command.Cheer(from = "엄마", text = "조심히 와~"))
        val e = sig(Signal.Speed(0f))
        assertTrue(e.none { it is Effect.PlayCheer || it is Effect.FamilyMessage })
        assertEquals(1, d.snapshot().pendingCheers)
    }

    @Test
    fun longDrivingGivesOneRestHintThenPlaysCheerAtRestStop() {
        cmd(Command.SetRestThreshold(seconds = 20))
        drive()
        cmd(Command.Cheer(from = "민지", text = "쉬었다 가세요"))
        now = 10_000
        assertTrue(d.onTick(now).isEmpty())
        now = 21_000
        val hint = d.onTick(now)
        assertTrue(hint.any { it is Effect.Speak && it.text.contains("쉬는 곳에 멈추면 들려 드릴게요") })
        now = 25_000
        assertTrue(d.onTick(now).none { it is Effect.Speak })
        now = 30_000
        val e = park()
        assertEquals(listOf("휴게소에서 쉬는 중이에요"), messages(e))
        assertTrue(Effect.PlayCheer("민지", "쉬었다 가세요") in e)
    }

    @Test
    fun restHintWithoutCheerSuggestsBreak() {
        cmd(Command.SetRestThreshold(seconds = 20))
        drive()
        now = 21_000
        assertTrue(d.onTick(now).any { it is Effect.Speak && it.text.contains("잠시 쉬어 가세요") })
    }

    @Test
    fun departingStopsCheerPlayback() {
        cmd(Command.Cheer(from = "엄마", text = "잘 다녀와"))
        val e = drive()
        assertTrue(Effect.StopVoice in e)
    }

    @Test
    fun batteryReachingTargetNotifiesOnce() {
        assertTrue(messages(sig(Signal.Battery(70f))).isEmpty())
        assertEquals(listOf("충전 80% 완료, 출발 가능"), messages(sig(Signal.Battery(80f))))
        assertTrue(messages(sig(Signal.Battery(82f))).isEmpty())
    }

    @Test
    fun resetClearsTripAndPickup() {
        drive(); acceptPickup()
        cmd(Command.Reset)
        val s = d.snapshot()
        assertEquals(PickupPhase.NONE, s.pickup)
        assertEquals(0, s.pendingCheers)
        assertTrue(messages(drive()).isEmpty())
    }
}
