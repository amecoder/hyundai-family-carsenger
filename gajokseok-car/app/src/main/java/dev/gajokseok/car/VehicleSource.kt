package dev.gajokseok.car

import ai.pleos.playground.vehicle.Vehicle
import ai.pleos.playground.vehicle.api.model.area.DoorArea
import ai.pleos.playground.vehicle.api.model.area.SeatArea
import ai.pleos.playground.vehicle.constant.area.DoorValue
import ai.pleos.playground.vehicle.constant.area.SeatValue
import ai.pleos.playground.vehicle.constant.control.VehicleGear
import ai.pleos.playground.vehicle.listener.DoorPositionListener
import ai.pleos.playground.vehicle.listener.EvBatteryStateOfChargeListener
import ai.pleos.playground.vehicle.listener.GearSelectionListener
import ai.pleos.playground.vehicle.listener.SeatOccupancyListener
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import dev.gajokseok.car.core.GearState
import dev.gajokseok.car.core.Side
import dev.gajokseok.car.core.Signal

private const val TAG = "GajokVehicle"

/**
 * Emulator v2.1.0 + Vehicle SDK 2.3.2 report seat occupancy inverted (VHAL 1=vacant arrives as true).
 * Verified 2026-10-26; flip this once Pleos confirms the fix.
 */
private const val SEAT_OCCUPANCY_INVERTED = true

/** Bridges Pleos Vehicle SDK listeners to [Signal]s, always delivered on the main thread. */
class VehicleSource(private val context: Context, private val onSignal: (Signal) -> Unit, private val onError: (String) -> Unit) {
    private val main = Handler(Looper.getMainLooper())
    private var vehicle: Vehicle? = null

    private fun emit(s: Signal) = main.post { onSignal(s) }

    private fun guard(name: String, block: () -> Unit) {
        runCatching(block).onFailure { e ->
            Log.e(TAG, "$name failed", e)
            main.post { onError("$name: ${e.message}") }
        }
    }

    fun start() {
        val v = Vehicle(context)
        vehicle = v
        guard("vehicle.initialize") { v.initialize() }
        guard("gear") {
            v.getGear().registerGearSelection(object : GearSelectionListener {
                override fun onFailed(p0: Exception) { Log.e(TAG, "gear", p0) }
                override fun onSelected(p0: VehicleGear?) { emit(Signal.Gear(map(p0))) }
            })
        }
        listOf(DoorValue.ROW_2_LEFT to Side.LEFT, DoorValue.ROW_2_RIGHT to Side.RIGHT).forEach { (door, side) ->
            guard("door $side") {
                v.getDoor().registerDoorPosition(DoorArea(door), object : DoorPositionListener {
                    override fun onFailed(p0: Exception) { Log.e(TAG, "door $side", p0) }
                    override fun onPositionUpdated(p0: Int?) { emit(Signal.RearDoor(side, open = (p0 ?: 0) > 0)) }
                })
            }
        }
        listOf(SeatValue.ROW_2_LEFT to Side.LEFT, SeatValue.ROW_2_RIGHT to Side.RIGHT).forEach { (seat, side) ->
            guard("seat $side") {
                v.getSeat().registerSeatOccupancy(SeatArea(seat), object : SeatOccupancyListener {
                    override fun onFailed(p0: Exception) { Log.e(TAG, "seat $side", p0) }
                    override fun onSeatOccupancyUpdated(p0: Boolean?) {
                        val raw = p0 ?: return
                        emit(Signal.RearSeat(side, occupied = if (SEAT_OCCUPANCY_INVERTED) !raw else raw))
                    }
                })
            }
        }
        guard("battery") {
            v.getEvBattery().registerEvBatteryStateOfCharge(object : EvBatteryStateOfChargeListener {
                override fun onFailed(p0: Exception) { Log.e(TAG, "battery", p0) }
                override fun onEvBatteryStateOfChargeUpdated(p0: Int?) { p0?.let { emit(Signal.Battery(it.toFloat())) } }
            })
        }
    }

    private fun map(g: VehicleGear?): GearState = when (g) {
        VehicleGear.GEAR_PARK -> GearState.PARK
        VehicleGear.GEAR_REVERSE -> GearState.REVERSE
        VehicleGear.GEAR_NEUTRAL -> GearState.NEUTRAL
        null, VehicleGear.GEAR_UNKNOWN -> GearState.UNKNOWN
        else -> GearState.DRIVE
    }

    fun stop() {
        runCatching { vehicle?.release() }
    }
}
