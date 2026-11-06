package dev.gajokseok.car.core

import kotlin.math.abs

/**
 * Spots the steering habit of a tired driver: the wheel stays still, then one sudden turn corrects the drift.
 * Direction is ignored because the emulator reports angles mirrored. The SDK only sends changes, so a still wheel means
 * no samples at all; [onTick] opens the still spell and closes a turn that has no sample after it. All thresholds are demo values, not validated
 * against real driving.
 */
class DrowsyPattern(
    private val stillMs: Long = 4_000,
    /** smaller moves than this still count as a still wheel */
    private val stillDeg: Float = 2f,
    private val turnDeg: Float = 15f,
    private val turnWindowMs: Long = 1_000,
) {
    private var stillSinceMs: Long? = null
    private var restAngle = 0f
    private var lastAngle = 0f
    private var turnStartMs: Long? = null
    private var stillBeforeTurn = false
    private var counted = false

    /** cruising = driving fast enough for lane keeping to matter; returns true the moment one pattern completes. */
    fun onAngle(deg: Float, nowMs: Long, cruising: Boolean): Boolean {
        lastAngle = deg
        if (!cruising) {
            reset()
            return false
        }
        val since = stillSinceMs
        if (since == null) {
            settle(nowMs)
            return false
        }
        val start = turnStartMs
        if (start == null) {
            if (abs(deg - restAngle) <= stillDeg) return false
            turnStartMs = nowMs
            stillBeforeTurn = nowMs - since >= stillMs
            counted = false
        } else if (nowMs - start > turnWindowMs) {
            settle(nowMs)
            return false
        }
        if (!stillBeforeTurn || counted || abs(deg - restAngle) < turnDeg) return false
        counted = true
        return true
    }

    /** A still wheel sends nothing, so the clock has to start and stop the still spell from here. */
    fun onTick(nowMs: Long, cruising: Boolean) {
        if (!cruising) {
            reset()
            return
        }
        if (stillSinceMs == null) {
            settle(nowMs)
            return
        }
        val start = turnStartMs ?: return
        if (nowMs - start > turnWindowMs) settle(nowMs)
    }

    fun reset() {
        stillSinceMs = null
        turnStartMs = null
        stillBeforeTurn = false
        counted = false
    }

    private fun settle(nowMs: Long) {
        stillSinceMs = nowMs
        restAngle = lastAngle
        turnStartMs = null
        stillBeforeTurn = false
        counted = false
    }
}
