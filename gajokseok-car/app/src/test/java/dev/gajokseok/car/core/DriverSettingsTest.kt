package dev.gajokseok.car.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class DriverSettingsTest {
    private lateinit var d: Detector
    private var now = 0L

    private fun sig(s: Signal): List<Effect> = d.onSignal(s, now)
    private fun cmd(c: Command): List<Effect> = d.onCommand(c, now)
    private fun speed(kph: Float) = sig(Signal.Speed(kph, atMs = now))

    @Before
    fun setUp() {
        d = Detector()
        now = 0L
        sig(Signal.Gear(GearState.PARK))
    }

    private fun twoHarshBrakes(): List<Effect> {
        sig(Signal.Gear(GearState.DRIVE))
        val out = mutableListOf<Effect>()
        repeat(2) {
            speed(80f); now += 1_000
            out += speed(20f); now += 4_000
        }
        return out
    }

    @Test
    fun everythingStartsOffBecauseTheDriverOptsIn() {
        assertEquals(DriverSettings(cheerVoice = false, safetyAlert = false, usageRecording = false), d.settings)
    }

    @Test
    fun cheerIsNotPlayedWhileTheDriverHasCheersOffAndTheFamilyIsTold() {
        sig(Signal.Gear(GearState.DRIVE))
        val e = cmd(Command.Cheer(from = "엄마", text = "조심히 와", audioUrl = "http://x/a"))
        assertTrue(e.none { it is Effect.PlayCheer })
        // reported back so the family's bubble stops waiting for playback
        assertEquals(listOf(Effect.CheerSkipped("엄마", "조심히 와")), e.filterIsInstance<Effect.CheerSkipped>())
        assertEquals(1, d.snapshot().cheersReceived)
    }

    @Test
    fun parkedCheerWithCheersOffShowsNoCheerCard() {
        val e = cmd(Command.Cheer(from = "엄마", text = "조심히 와", audioUrl = "http://x/a"))
        assertTrue(e.none { it == Effect.ShowScreen(Screen.CHEER) })
    }

    @Test
    fun turningCheersOnPlaysTheNextCheer() {
        d.updateSettings(d.settings.copy(cheerVoice = true))
        val e = cmd(Command.Cheer(from = "엄마", text = "조심히 와", audioUrl = "http://x/a"))
        assertTrue(e.any { it is Effect.PlayCheer })
    }

    @Test
    fun safetyAlertStaysOffButRiskyMomentsAreStillCounted() {
        val e = twoHarshBrakes()
        assertTrue(e.none { it is Effect.SafetyAlert })
        assertEquals(2, d.snapshot().harshBrakes)
    }

    @Test
    fun safetyAlertGoesOutOnceTheDriverTurnsItOn() {
        d.updateSettings(d.settings.copy(safetyAlert = true))
        assertEquals(1, twoHarshBrakes().count { it is Effect.SafetyAlert })
    }

    @Test
    fun usageEventNamesAreDroppedUntilTheDriverAgreesToTheLog() {
        assertNull(d.settings.usageEvent(UsageEvent.TRIP_DEPARTED))
        d.updateSettings(d.settings.copy(usageRecording = true))
        assertEquals(UsageEvent.TRIP_DEPARTED, d.settings.usageEvent(UsageEvent.TRIP_DEPARTED))
    }

    @Test
    fun runnerStandInChangesTheSettingsAndSaysSoInTheLog() {
        val e = cmd(Command.ApplyDriverSettings(cheerVoice = true, safetyAlert = true))
        assertEquals(DriverSettings(cheerVoice = true, safetyAlert = true, usageRecording = false), d.settings)
        assertTrue(e.any { it is Effect.Note && it.text.contains("운전자 설정") })
    }

    @Test
    fun runnerStandInLeavesTheDriversUsageChoiceAlone() {
        d.updateSettings(DriverSettings(usageRecording = true))
        cmd(Command.ApplyDriverSettings(cheerVoice = false, safetyAlert = false))
        assertTrue(d.settings.usageRecording)
        cmd(Command.ApplyDriverSettings(cheerVoice = false, safetyAlert = false, usageRecording = false))
        assertFalse(d.settings.usageRecording)
    }

    @Test
    fun aRemoteCommandCannotTurnTheUsageLogOn() {
        // only the driver's own switch opts in; a remote command may only opt out
        cmd(Command.ApplyDriverSettings(cheerVoice = true, safetyAlert = true, usageRecording = true))
        assertFalse(d.settings.usageRecording)
        assertTrue(d.settings.cheerVoice)
    }

    @Test
    fun resetKeepsTheDriversChoice() {
        d.updateSettings(DriverSettings(cheerVoice = true))
        cmd(Command.Reset)
        assertTrue(d.settings.cheerVoice)
        assertFalse(d.settings.safetyAlert)
    }
}
