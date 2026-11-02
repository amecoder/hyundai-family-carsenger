package dev.gajokseok.car.core

/**
 * The driver's own switches. Plan v0.6 makes 기능 ③·④ opt-in, so everything starts off.
 * cheerVoice = family voice cheers play in the car; safetyAlert = repeated risky driving is reported to the family room;
 * usageRecording = the car names its events for the retention log (the family app asks its members separately).
 */
data class DriverSettings(
    val cheerVoice: Boolean = false,
    val safetyAlert: Boolean = false,
    val usageRecording: Boolean = false,
) {
    /** The usage event to send with a message, or null while the driver has not agreed to the log. */
    fun usageEvent(event: String?): String? = event.takeIf { usageRecording }

    fun summary(): String = listOf(
        "응원 듣기" to cheerVoice, "안전 운전 응원" to safetyAlert, "사용 기록" to usageRecording,
    ).joinToString(" · ") { (name, on) -> "$name ${if (on) "켬" else "끔"}" }
}
