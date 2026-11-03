package dev.gajokseok.car

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView

// Small view-building helpers so screens can be declared in Kotlin without XML.

/**
 * Hyundai CI colors (hyundai.com/kr/ko/info/ci/ci-color) on a deep-navy dark theme. Surfaces step up in lightness
 * the higher they sit (Material dark elevation); bg/panels/muted/red/sandSoft are derived, not official CI values.
 */
object Palette {
    val bg = Color.parseColor("#000D1C")
    val panel = Color.parseColor("#0D1927")
    val panel2 = Color.parseColor("#1C2835")
    val line = Color.parseColor("#2A3541")
    val ink = Color.parseColor("#FFFFFF")
    val muted = Color.parseColor("#A09E9C")
    val accent = Color.parseColor("#00AAD2") // Active Blue: the one primary action, navy text on it
    val brand = Color.parseColor("#002C5F") // Hyundai Blue: highlighted cards
    val sky = Color.parseColor("#AACAE6") // Sky Blue: text on Hyundai Blue
    val sand = Color.parseColor("#E4DCD3") // Sand: family side
    val sandSoft = Color.parseColor("#27303C")
    val red = Color.parseColor("#EF7A65")
}

private var fonts: Pair<Typeface, Typeface>? = null

/** Asta Sans (SIL OFL, assets/fonts/OFL.txt), Pleos Connect's system font; one variable file, two weights. */
fun Context.font(bold: Boolean): Typeface {
    val pair = fonts ?: Pair(
        Typeface.Builder(assets, "fonts/AstaSans.ttf").setFontVariationSettings("'wght' 400").build(),
        Typeface.Builder(assets, "fonts/AstaSans.ttf").setFontVariationSettings("'wght' 650").build(),
    ).also { fonts = it }
    return if (bold) pair.second else pair.first
}

/** [top] laid over [base] at [alpha] (0..1), as an opaque color: Material's pressed-state layer. */
fun overlay(top: Int, base: Int, alpha: Float): Int {
    fun mix(shift: Int) = ((top shr shift and 0xFF) * alpha + (base shr shift and 0xFF) * (1 - alpha)).toInt()
    return Color.rgb(mix(16), mix(8), mix(0))
}

/** Material elevation: a soft shadow under cards that sit above the screen. */
fun View.raise(level: Int) {
    elevation = context.dp(level * 4).toFloat()
}

/** Text is viewed shrunk inside the runner page, so everything is drawn larger than a phone UI would be. */
const val TEXT_SCALE = 1.35f

fun Context.dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

fun rounded(color: Int, radius: Float, stroke: Int? = null): GradientDrawable = GradientDrawable().apply {
    setColor(color)
    cornerRadius = radius
    stroke?.let { setStroke(2, it) }
}

fun Context.label(text: String, size: Float, color: Int = Palette.ink, bold: Boolean = false): TextView = TextView(this).apply {
    this.text = text
    textSize = size * TEXT_SCALE
    setTextColor(color)
    typeface = font(bold)
}

fun Context.column(padding: Int = 0, gap: Int = 0): LinearLayout = LinearLayout(this).apply {
    orientation = LinearLayout.VERTICAL
    setPadding(dp(padding), dp(padding), dp(padding), dp(padding))
    if (gap > 0) {
        showDividers = LinearLayout.SHOW_DIVIDER_MIDDLE
        dividerDrawable = GradientDrawable().apply { setSize(1, dp(gap)); setColor(Color.TRANSPARENT) }
    }
}

fun Context.row(gap: Int = 0): LinearLayout = column(0, 0).apply {
    orientation = LinearLayout.HORIZONTAL
    gravity = Gravity.CENTER_VERTICAL
    if (gap > 0) {
        showDividers = LinearLayout.SHOW_DIVIDER_MIDDLE
        dividerDrawable = GradientDrawable().apply { setSize(dp(gap), 1); setColor(Color.TRANSPARENT) }
    }
}

fun lp(w: Int = ViewGroup.LayoutParams.MATCH_PARENT, h: Int = ViewGroup.LayoutParams.WRAP_CONTENT, weight: Float = 0f) =
    LinearLayout.LayoutParams(w, h, weight)

fun View.gone(hidden: Boolean) {
    visibility = if (hidden) View.GONE else View.VISIBLE
}
