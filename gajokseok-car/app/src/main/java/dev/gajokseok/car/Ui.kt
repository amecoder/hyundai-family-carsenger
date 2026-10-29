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

object Palette {
    val bg = Color.parseColor("#0B1220")
    val panel = Color.parseColor("#121E2E")
    val panel2 = Color.parseColor("#182638")
    val line = Color.parseColor("#29374C")
    val ink = Color.parseColor("#EDF3FB")
    val muted = Color.parseColor("#8C99AE")
    val amber = Color.parseColor("#F2A23A")
    val amberSoft = Color.parseColor("#332719")
    val amberInk = Color.parseColor("#FFD9A0")
    val teal = Color.parseColor("#47BDB3")
    val tealSoft = Color.parseColor("#163330")
    val tealInk = Color.parseColor("#B5EEE7")
    val green = Color.parseColor("#58D0A5")
    val red = Color.parseColor("#FF8A7A")
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
    if (bold) typeface = Typeface.DEFAULT_BOLD
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
