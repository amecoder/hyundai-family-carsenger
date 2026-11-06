package dev.gajokseok.car.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class DrowsyPatternTest {
    private lateinit var p: DrowsyPattern

    @Before
    fun setUp() {
        p = DrowsyPattern()
        p.onAngle(0f, 0L, cruising = true)
    }

    @Test
    fun stillWheelThenSuddenTurnIsOnePattern() {
        assertTrue(p.onAngle(20f, 5_000L, cruising = true))
    }

    @Test
    fun suddenTurnAfterAShortStillSpellIsNormalDriving() {
        assertFalse(p.onAngle(20f, 3_000L, cruising = true))
    }

    @Test
    fun smallCorrectionsAreNotPatterns() {
        assertFalse(p.onAngle(1f, 5_000L, cruising = true))
        assertFalse(p.onAngle(-1f, 9_000L, cruising = true))
    }

    @Test
    fun steadyActiveSteeringNeverCounts() {
        var t = 0L
        var hits = 0
        repeat(40) { i ->
            t += 1_500
            p.onTick(t, cruising = true)
            if (p.onAngle(if (i % 2 == 0) 6f else -6f, t, cruising = true)) hits += 1
        }
        assertEquals(0, hits)
    }

    @Test
    fun slowCurveIsNotASuddenTurn() {
        assertFalse(p.onAngle(5f, 5_000L, cruising = true))
        p.onTick(6_200L, cruising = true)
        assertFalse(p.onAngle(20f, 6_300L, cruising = true))
    }

    @Test
    fun theTurnMayBuildUpOverSeveralSamples() {
        assertFalse(p.onAngle(6f, 5_000L, cruising = true))
        assertTrue(p.onAngle(18f, 5_400L, cruising = true))
    }

    @Test
    fun direction_doesNotMatter_theSdkReportsMirroredAngles() {
        assertTrue(p.onAngle(-20f, 5_000L, cruising = true))
    }

    @Test
    fun oneSwerveCountsOnce() {
        assertTrue(p.onAngle(20f, 5_000L, cruising = true))
        assertFalse(p.onAngle(30f, 5_200L, cruising = true))
        assertFalse(p.onAngle(0f, 5_500L, cruising = true))
    }

    @Test
    fun theNextPatternNeedsAStillSpellAgain() {
        assertTrue(p.onAngle(20f, 5_000L, cruising = true))
        p.onTick(6_100L, cruising = true)
        assertFalse(p.onAngle(0f, 7_000L, cruising = true))
        p.onTick(8_100L, cruising = true)
        assertTrue(p.onAngle(20f, 12_200L, cruising = true))
    }

    @Test
    fun turnsAtLowSpeedAreIgnored() {
        assertFalse(p.onAngle(90f, 5_000L, cruising = false))
    }

    @Test
    fun stillTimeBelowCruisingSpeedDoesNotCount() {
        p.onAngle(0f, 5_000L, cruising = false)
        assertFalse(p.onAngle(20f, 5_100L, cruising = true))
    }

    @Test
    fun aStillWheelSendsNoSamplesSoTheTickStartsTheStillSpell() {
        val q = DrowsyPattern()
        q.onTick(0L, cruising = true)
        assertTrue(q.onAngle(25f, 6_000L, cruising = true))
    }

    @Test
    fun stoppedTimeWithoutSamplesIsNotAStillWheel() {
        p.onTick(5_000L, cruising = false)
        p.onTick(6_000L, cruising = true)
        assertFalse(p.onAngle(20f, 7_000L, cruising = true))
    }

    @Test
    fun resetForgetsTheStillSpell() {
        p.reset()
        p.onAngle(0f, 5_000L, cruising = true)
        assertFalse(p.onAngle(20f, 6_000L, cruising = true))
    }
}
