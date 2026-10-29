package dev.gajokseok.car

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Shader
import android.view.View

/** The family's own car shown on the home screen. Drawn in code (no manufacturer artwork or logo). */
object MyCar {
    const val MODEL = "투싼"
    const val COLOR_NAME = "그레이"
    val body = Color.parseColor("#B4BAC2")
    val bodyDark = Color.parseColor("#80868F")
}

/** Side view of a compact SUV in the car's color: long hood, upright cabin, roof rails, full-width front light bar. */
class CarView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val path = Path()

    // Shape is laid out on a 100 x 42 grid and scaled to the view.
    override fun onDraw(canvas: Canvas) {
        val sx = width / 100f
        val sy = height / 42f
        fun x(v: Float) = v * sx
        fun y(v: Float) = v * sy

        // ground shadow
        paint.shader = null
        paint.color = Color.argb(70, 0, 0, 0)
        canvas.drawOval(RectF(x(6f), y(37f), x(94f), y(41.5f)), paint)

        // body
        path.reset()
        path.moveTo(x(4f), y(29f))
        path.lineTo(x(4.5f), y(22f))
        path.quadTo(x(6f), y(18.5f), x(14f), y(17.5f))   // rear bumper up to tailgate
        path.lineTo(x(18f), y(6f))                         // rear pillar
        path.quadTo(x(19.5f), y(3.5f), x(25f), y(3.5f))
        path.lineTo(x(58f), y(3.5f))                       // roof
        path.quadTo(x(62f), y(3.7f), x(65f), y(6.5f))
        path.lineTo(x(74f), y(16f))                        // windshield
        path.lineTo(x(91f), y(18f))                        // hood
        path.quadTo(x(96f), y(19f), x(96.5f), y(23f))
        path.lineTo(x(96f), y(30f))
        path.quadTo(x(95.5f), y(33f), x(92f), y(33f))
        path.lineTo(x(8f), y(33f))
        path.quadTo(x(4.5f), y(33f), x(4f), y(30f))
        path.close()
        paint.color = Color.WHITE // shader takes its alpha from the paint; the shadow above left it at 70
        paint.shader = LinearGradient(0f, y(6f), 0f, y(33f), MyCar.body, MyCar.bodyDark, Shader.TileMode.CLAMP)
        canvas.drawPath(path, paint)
        paint.shader = null

        // lower cladding
        paint.color = Color.parseColor("#2E3238")
        canvas.drawRect(x(8f), y(29.5f), x(92f), y(33f), paint)

        // windows
        paint.color = Color.parseColor("#3B4A5C")
        path.reset()
        path.moveTo(x(21.5f), y(16.5f))
        path.lineTo(x(24f), y(7f))
        path.quadTo(x(25f), y(5.8f), x(27f), y(5.8f))
        path.lineTo(x(57f), y(5.8f))
        path.quadTo(x(60f), y(6f), x(62f), y(8f))
        path.lineTo(x(69.5f), y(16.5f))
        path.close()
        canvas.drawPath(path, paint)
        // B and C pillars
        paint.color = MyCar.bodyDark
        canvas.drawRect(x(44f), y(5.8f), x(46f), y(16.5f), paint)
        canvas.drawRect(x(30f), y(5.8f), x(31.5f), y(16.5f), paint)

        // roof rail
        paint.color = Color.parseColor("#3A3F46")
        canvas.drawRoundRect(RectF(x(23f), y(1.6f), x(60f), y(3.2f)), y(0.7f), y(0.7f), paint)

        // door line and handles
        paint.color = Color.argb(90, 0, 0, 0)
        canvas.drawRect(x(45f), y(17f), x(45.4f), y(29.5f), paint)
        canvas.drawRect(x(31f), y(17f), x(31.4f), y(29.5f), paint)
        paint.color = Color.argb(140, 255, 255, 255)
        canvas.drawRoundRect(RectF(x(37f), y(19f), x(41f), y(19.9f)), y(0.4f), y(0.4f), paint)
        canvas.drawRoundRect(RectF(x(51f), y(19f), x(55f), y(19.9f)), y(0.4f), y(0.4f), paint)

        // front light bar and rear lamp
        paint.color = Color.parseColor("#E9F4FF")
        canvas.drawRoundRect(RectF(x(88f), y(19.2f), x(96.2f), y(20.6f)), y(0.7f), y(0.7f), paint)
        paint.color = Color.parseColor("#D9443A")
        canvas.drawRoundRect(RectF(x(4.6f), y(19.5f), x(9f), y(21f)), y(0.7f), y(0.7f), paint)

        // wheels
        for (cx in floatArrayOf(22f, 78f)) {
            paint.color = Color.parseColor("#15181C")
            canvas.drawCircle(x(cx), y(32f), y(8f), paint)
            paint.color = Color.parseColor("#B9BEC5")
            canvas.drawCircle(x(cx), y(32f), y(4.6f), paint)
            paint.color = Color.parseColor("#4A4F57")
            canvas.drawCircle(x(cx), y(32f), y(1.6f), paint)
        }
    }
}
