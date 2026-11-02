package dev.gajokseok.car

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.Switch
import dev.gajokseok.car.core.DriverSettings

/** Keeps the driver's switches across app restarts and reinstalls (adb install -r keeps app data). */
class DriverSettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences("driver_settings", Context.MODE_PRIVATE)

    fun load() = DriverSettings(
        cheerVoice = prefs.getBoolean(CHEER_VOICE, false),
        safetyAlert = prefs.getBoolean(SAFETY_ALERT, false),
        usageRecording = prefs.getBoolean(USAGE_RECORDING, false),
    )

    fun save(s: DriverSettings) {
        prefs.edit()
            .putBoolean(CHEER_VOICE, s.cheerVoice)
            .putBoolean(SAFETY_ALERT, s.safetyAlert)
            .putBoolean(USAGE_RECORDING, s.usageRecording)
            .apply()
    }

    private companion object {
        const val CHEER_VOICE = "cheer_voice"
        const val SAFETY_ALERT = "safety_alert"
        const val USAGE_RECORDING = "usage_recording"
    }
}

/**
 * The driver's settings card (기능 ③·④ opt-in and the usage log). Shown only while parked: Pleos covers
 * third-party screens while driving, and settings must never be touched on the move.
 */
class DriverSettingsCard(
    private val context: Context,
    private val onChange: (DriverSettings) -> Unit,
    private val onClose: () -> Unit,
) {
    private lateinit var cheerSwitch: Switch
    private lateinit var safetySwitch: Switch
    private lateinit var usageSwitch: Switch
    /** set while show() fills the switches, so filling them does not count as the driver's change */
    private var filling = false

    val view: View = build()

    fun show(s: DriverSettings) {
        filling = true
        cheerSwitch.isChecked = s.cheerVoice
        safetySwitch.isChecked = s.safetyAlert
        usageSwitch.isChecked = s.usageRecording
        filling = false
        view.gone(false)
    }

    private fun current() = DriverSettings(cheerSwitch.isChecked, safetySwitch.isChecked, usageSwitch.isChecked)

    private fun build(): View = with(context) {
        val card = column(padding = 36, gap = 20).apply {
            background = rounded(Palette.panel2, dp(28).toFloat(), Palette.teal)
            isClickable = true // taps on the card must not fall through to the home screen behind it
        }
        card.addView(label("⚙ 운전자 설정", 18f, Palette.teal, bold = true))
        card.addView(label("켠 기능만 작동합니다. 언제든 끌 수 있어요.", 22f, bold = true))
        cheerSwitch = settingRow(card, "가족 목소리 바로 듣기", "가족이 보낸 응원 음성을 주행 중에도 차 스피커로 바로 재생")
        safetySwitch = settingRow(card, "안전 운전 응원", "한 주행에 급제동·과속이 합쳐 2번이면 가족방에 한 번 알림")
        usageSwitch = settingRow(card, "서비스 개선용 사용 기록", "기능 이름과 시각만 가명으로 저장 · 위치·메시지·음성은 저장 안 함")
        card.addView(Button(this).apply {
            text = "닫기"
            textSize = 22f
            isAllCaps = false
            setTextColor(Palette.ink)
            background = rounded(Palette.panel, dp(18).toFloat(), Palette.line)
            setOnClickListener { onClose() }
        }, lp(MATCH, dp(70)))
        card
    }

    private fun Context.settingRow(parent: LinearLayout, title: String, detail: String): Switch {
        val r = row(gap = 20).apply {
            background = rounded(Palette.panel, dp(16).toFloat())
            setPadding(dp(20), dp(14), dp(20), dp(14))
        }
        val text = column()
        text.addView(label(title, 22f, bold = true))
        text.addView(label(detail, 15f, Palette.muted))
        r.addView(text, lp(0, WRAP, 1f))
        val sw = Switch(this).apply {
            contentDescription = title
            thumbTintList = ColorStateList(arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()), intArrayOf(Palette.teal, Color.LTGRAY))
            setOnCheckedChangeListener { _, _ -> if (!filling) onChange(current()) }
        }
        r.addView(sw, lp(WRAP))
        parent.addView(r)
        return sw
    }

    private companion object {
        const val MATCH = LinearLayout.LayoutParams.MATCH_PARENT
        const val WRAP = LinearLayout.LayoutParams.WRAP_CONTENT
    }
}
