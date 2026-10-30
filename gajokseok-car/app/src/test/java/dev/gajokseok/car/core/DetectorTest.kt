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
        cmd(Command.SetTrip(origin = "회사", destination = "집", etaMin = 40, driver = "아빠", child = "민지"))
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
        assertEquals(listOf("아빠 회사에서 출발, 40분 뒤 집 도착 예정"), messages(e))
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
    fun cheerWhileDrivingPlaysRightAway() {
        drive()
        val e = cmd(Command.Cheer(from = "엄마", text = "조심히 와~"))
        assertTrue(Effect.PlayCheer("엄마", "조심히 와~") in e)
        // Pleos covers third-party screens while driving, so the driving screen stays and only the voice plays
        assertFalse(Effect.ShowScreen(Screen.CHEER) in e)
        assertEquals(1, d.snapshot().cheersReceived)
    }

    @Test
    fun cheerWhileParkedPlaysAndShowsTheCard() {
        val e = cmd(Command.Cheer(from = "엄마", text = "잘 다녀와"))
        assertTrue(Effect.PlayCheer("엄마", "잘 다녀와") in e)
        assertTrue(Effect.ShowScreen(Screen.CHEER) in e)
    }

    @Test
    fun recordedCheerPlaysItsClipWhileDriving() {
        drive()
        val url = "http://10.0.2.2:8090/api/audio/abc123"
        val e = cmd(Command.Cheer(from = "엄마", text = "조심히 와", audioUrl = url, durationMs = 4200))
        assertTrue(Effect.PlayCheer("엄마", "조심히 와", audioUrl = url, durationMs = 4200) in e)
    }

    @Test
    fun everyCheerInARowIsPlayed() {
        drive()
        val played = (0 until 4).flatMap { cmd(Command.Cheer(from = "엄마", text = "응원 $it")) }.filterIsInstance<Effect.PlayCheer>()
        assertEquals(listOf("응원 0", "응원 1", "응원 2", "응원 3"), played.map { it.text })
    }

    @Test
    fun homeArrivalAfterBoardingAnnouncesParking() {
        drive(); acceptPickup(); park(); board()
        drive()
        val e = park()
        assertEquals(listOf("집에 도착해서 주차했어요"), messages(e))
    }

    @Test
    fun secondDepartureWithChildAboardMentionsChild() {
        drive(); acceptPickup(); park(); board()
        val e = drive()
        assertEquals(listOf("민지와 함께 집으로 출발"), messages(e))
    }

    @Test
    fun destinationWithoutFinalConsonantTakesRo() {
        cmd(Command.SetTrip(origin = "집", destination = "마트", etaMin = 10, driver = "아빠", child = "민지"))
        drive(); acceptPickup(); park(); board()
        assertEquals(listOf("민지와 함께 마트로 출발"), messages(drive()))
    }

    @Test
    fun longDrivingGivesOneRestHintThenAnnouncesTheRestStop() {
        cmd(Command.SetRestThreshold(seconds = 20))
        drive()
        now = 10_000
        assertTrue(d.onTick(now).isEmpty())
        now = 21_000
        assertTrue(d.onTick(now).any { it is Effect.Speak && it.text == "오래 운전하셨어요. 잠시 쉬어 가세요." })
        now = 25_000
        assertTrue(d.onTick(now).none { it is Effect.Speak })
        now = 30_000
        assertEquals(listOf("휴게소에서 쉬는 중이에요"), messages(park()))
    }

    @Test
    fun departingKeepsACheerPlaying() {
        cmd(Command.Cheer(from = "엄마", text = "잘 다녀와"))
        assertFalse(Effect.StopVoice in drive())
    }

    private fun speed(kph: Float, atMs: Long): List<Effect> { now = atMs; return sig(Signal.Speed(kph)) }

    // 90 -> 10 km/h within a second: 80 km/h per second, far past an ordinary stop
    private fun harshBrake(atMs: Long): List<Effect> = speed(90f, atMs) + speed(10f, atMs + 1_000)

    @Test
    fun suddenSpeedDropCountsAsHarshBraking() {
        drive()
        harshBrake(1_000)
        assertEquals(1, d.snapshot().harshBrakes)
    }

    @Test
    fun ordinaryStopIsNotHarshBraking() {
        drive()
        // 50 -> 0 km/h over 3 s, the way the demo scenarios stop
        (0..10).forEach { speed(50f - it * 5f, 1_000L + it * 300) }
        assertEquals(0, d.snapshot().harshBrakes)
    }

    @Test
    fun samplesArrivingCloseTogetherDoNotInflateTheBrakingRate() {
        drive()
        speed(60f, 1_000); speed(54f, 2_000); speed(48f, 2_100)
        assertEquals(0, d.snapshot().harshBrakes)
    }

    @Test
    fun brakingIsMeasuredWithTheSensorTimestampNotTheDeliveryTime() {
        drive()
        now = 5_000
        sig(Signal.Speed(90f, atMs = 1_000))
        sig(Signal.Speed(10f, atMs = 2_000))
        assertEquals(1, d.snapshot().harshBrakes)
    }

    @Test
    fun brakingFromLowSpeedIsIgnored() {
        drive()
        speed(15f, 1_000); speed(0f, 1_300)
        assertEquals(0, d.snapshot().harshBrakes)
    }

    @Test
    fun speedingCountsOnceAfterTenSecondsAndAgainAfterSlowingDown() {
        drive()
        (0..12).forEach { speed(120f, 1_000L + it * 1_000) }
        assertEquals(1, d.snapshot().speedings)
        speed(90f, 15_000)
        (0..10).forEach { speed(118f, 16_000L + it * 1_000) }
        assertEquals(2, d.snapshot().speedings)
    }

    @Test
    fun shortBurstOverTheLimitIsNotSpeeding() {
        drive()
        (0..5).forEach { speed(120f, 1_000L + it * 1_000) }
        speed(100f, 7_000)
        assertEquals(0, d.snapshot().speedings)
    }

    @Test
    fun dippingBelowTheLimitRestartsTheTenSecondClock() {
        drive()
        (0..4).forEach { speed(111f, 1_000L + it * 1_000) }
        speed(105f, 6_000)
        (0..4).forEach { speed(111f, 7_000L + it * 1_000) }
        assertEquals(0, d.snapshot().speedings)
    }

    @Test
    fun aSampleArrivingOutOfOrderIsIgnored() {
        drive()
        sig(Signal.Speed(90f, atMs = 2_000))
        sig(Signal.Speed(10f, atMs = 1_000))
        assertEquals(90f, d.snapshot().speedKph)
        assertEquals(0, d.snapshot().harshBrakes)
    }

    @Test
    fun aTimestampFarFromNowFallsBackToTheArrivalTime() {
        drive()
        now = 100_000
        sig(Signal.Speed(90f, atMs = 5_000))
        now = 101_000
        sig(Signal.Speed(10f, atMs = 5_000))
        assertEquals(1, d.snapshot().harshBrakes)
    }

    @Test
    fun goingThroughNeutralDoesNotStartANewDrive() {
        drive()
        harshBrake(1_000)
        sig(Signal.Gear(GearState.NEUTRAL))
        drive()
        val alert = harshBrake(10_000).filterIsInstance<Effect.SafetyAlert>()
        assertEquals(1, alert.size)
        assertEquals(2, d.snapshot().harshBrakes)
    }

    @Test
    fun secondRiskyMomentSendsOneSafetyAlertToTheFamily() {
        drive()
        assertTrue(harshBrake(1_000).none { it is Effect.SafetyAlert })
        val alert = harshBrake(10_000).filterIsInstance<Effect.SafetyAlert>()
        assertEquals(listOf("운전 중 급제동이 2번 있었어요. 응원 한마디 보내 줄래요?"), alert.map { it.text })
        assertTrue(harshBrake(20_000).none { it is Effect.SafetyAlert })
    }

    @Test
    fun safetyAlertNamesBothKindsOfRiskyMoments() {
        drive()
        harshBrake(1_000)
        val e = (0..10).flatMap { speed(120f, 5_000L + it * 1_000) }
        assertEquals(listOf("운전 중 급제동 1번, 과속 1번이 있었어요. 응원 한마디 보내 줄래요?"),
            e.filterIsInstance<Effect.SafetyAlert>().map { it.text })
    }

    @Test
    fun riskyMomentsAreCountedPerDrive() {
        drive(); harshBrake(1_000); park()
        drive()
        assertEquals(0, d.snapshot().harshBrakes)
        assertTrue(harshBrake(10_000).none { it is Effect.SafetyAlert })
    }

    @Test
    fun batteryReachingTargetNotifiesOnce() {
        assertTrue(messages(sig(Signal.Battery(70f))).isEmpty())
        assertEquals(listOf("충전 80% 완료, 출발 가능"), messages(sig(Signal.Battery(80f))))
        assertTrue(messages(sig(Signal.Battery(82f))).isEmpty())
    }

    @Test
    fun acceptingPickupWithCoordinatesAddsNavigationWaypoint() {
        drive()
        cmd(Command.PickupRequest(by = "민지", place = "○○수학학원 앞", etaMin = 12, lat = 37.3947, lon = 127.1112))
        val e = cmd(Command.DriverReply(accept = true))
        assertTrue(Effect.AddWaypoint("○○수학학원 앞", 37.3947, 127.1112) in e)
    }

    @Test
    fun acceptingPickupWithoutCoordinatesOnlySpeaks() {
        drive()
        cmd(Command.PickupRequest(by = "민지", place = "직접 쓴 장소", etaMin = 12))
        val e = cmd(Command.DriverReply(accept = true))
        assertTrue(e.none { it is Effect.AddWaypoint })
        assertEquals(PickupPhase.ACCEPTED, d.snapshot().pickup)
    }

    @Test
    fun pickupRequestListensForTheDriversSpokenReply() {
        drive()
        val e = cmd(Command.PickupRequest(by = "민지", place = "○○수학학원 앞", etaMin = 12))
        assertTrue(Effect.ListenForReply in e)
    }

    @Test
    fun noReplyWithinTheTimeoutDeclinesThePickup() {
        drive()
        cmd(Command.PickupRequest(by = "민지", place = "○○수학학원 앞", etaMin = 12))
        now = 11_000
        assertTrue(messages(d.onTick(now)).isEmpty())
        now = 12_000
        val e = d.onTick(now)
        assertEquals(listOf("지금은 들를 수 없어요. 조금만 기다려 줘"), messages(e))
        assertTrue(e.any { it is Effect.Speak && it.text.contains("답이 없어") })
        assertEquals(PickupPhase.NONE, d.snapshot().pickup)
        assertTrue(cmd(Command.DriverReply(accept = true)).isEmpty())
    }

    @Test
    fun answeredPickupIsNotTimedOutLater() {
        drive()
        cmd(Command.PickupRequest(by = "민지", place = "○○수학학원 앞", etaMin = 12))
        now = 3_000
        cmd(Command.DriverReply(accept = true))
        now = 20_000
        assertTrue(messages(d.onTick(now)).isEmpty())
        assertEquals(PickupPhase.ACCEPTED, d.snapshot().pickup)
    }

    @Test
    fun anyAnswerOrTimeoutStopsListening() {
        drive()
        cmd(Command.PickupRequest(by = "민지", place = "○○수학학원 앞", etaMin = 12))
        assertTrue(Effect.StopListening in cmd(Command.DriverReply(accept = true)))
        cmd(Command.PickupRequest(by = "민지", place = "○○수학학원 앞", etaMin = 12))
        assertTrue(Effect.StopListening in cmd(Command.DriverReply(accept = false)))
        cmd(Command.PickupRequest(by = "민지", place = "○○수학학원 앞", etaMin = 12))
        now = 12_000
        assertTrue(Effect.StopListening in d.onTick(now))
    }

    @Test
    fun resetClearsTripAndPickup() {
        drive(); acceptPickup()
        cmd(Command.Reset)
        val s = d.snapshot()
        assertEquals(PickupPhase.NONE, s.pickup)
        assertEquals(0, s.cheersReceived)
        assertEquals(0, s.harshBrakes)
        assertTrue(messages(drive()).isEmpty())
    }
}
