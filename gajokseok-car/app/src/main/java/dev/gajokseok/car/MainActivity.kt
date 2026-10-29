package dev.gajokseok.car

import android.animation.ValueAnimator
import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import dev.gajokseok.car.core.Command
import dev.gajokseok.car.core.Detector
import dev.gajokseok.car.core.Effect
import dev.gajokseok.car.core.GearState
import dev.gajokseok.car.core.PickupPhase
import dev.gajokseok.car.core.Screen
import dev.gajokseok.car.core.Signal
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private const val TAG = "Gajokseok"

class MainActivity : Activity() {
    private val main = Handler(Looper.getMainLooper())
    private val detector = Detector()
    private lateinit var vehicle: VehicleSource
    private lateinit var link: FamilyLink
    private lateinit var voice: Voice
    private lateinit var cheers: CheerPlayer
    private val clock = SimpleDateFormat("HH:mm", Locale.KOREA)

    private lateinit var home: View
    private lateinit var driving: View
    private lateinit var timeline: LinearLayout
    private lateinit var timelineScroll: ScrollView
    private lateinit var statusPill: TextView
    private lateinit var stateValue: TextView
    private lateinit var tripValue: TextView
    private lateinit var pickupValue: TextView
    private lateinit var cheerValue: TextView
    private lateinit var linkValue: TextView
    private lateinit var noteBar: TextView
    private lateinit var driveBanner: TextView
    private lateinit var driveLast: TextView
    private lateinit var pickupCard: View
    private lateinit var pickupText: TextView
    private lateinit var cheerCard: View
    private lateinit var cheerTitle: TextView
    private lateinit var cheerText: TextView
    private lateinit var cheerMeta: TextView
    private val bars = mutableListOf<View>()
    private var barAnimator: ValueAnimator? = null
    private var speedKph = 0f

    private val tick = object : Runnable {
        override fun run() {
            apply(detector.onTick(SystemClock.elapsedRealtime()))
            main.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildRoot())
        requestPermissions(
            arrayOf(
                "pleos.car.permission.CAR_DRIVE", "pleos.car.permission.CAR_DOORS",
                "pleos.car.permission.CAR_SEATS", "pleos.car.permission.CAR_ENERGY",
                "android.car.permission.CAR_SPEED", "pleos.car.permission.TTS_SERVICE",
            ),
            1,
        )
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        val denied = permissions.filterIndexed { i, _ -> grantResults.getOrNull(i) != 0 }
        if (denied.isNotEmpty()) showNote("권한 거부: ${denied.joinToString { it.substringAfterLast('.') }} → 해당 신호 없이 동작")
        startSources()
    }

    private fun startSources() {
        voice = Voice(this) { ok, err -> main.post { if (!ok) showNote("음성 합성(TTS)을 쓸 수 없어 화면 문구로만 안내합니다 ($err)") } }
        cheers = CheerPlayer(voice, onStart = ::showCheer, onIdle = ::hideCheer)
        link = FamilyLink(
            onCommand = ::handleCommand,
            onConnection = { ok -> linkValue.text = if (ok) "● 가족 서버 연결됨" else "○ 가족 서버 연결 안 됨"; linkValue.setTextColor(if (ok) Palette.green else Palette.red) },
        )
        vehicle = VehicleSource(this, ::handleSignal) { msg -> showNote("차량 신호 오류: $msg") }
        vehicle.start()
        link.start()
        main.post(tick)
    }

    override fun onDestroy() {
        main.removeCallbacksAndMessages(null)
        if (::vehicle.isInitialized) vehicle.stop()
        if (::link.isInitialized) link.stop()
        if (::cheers.isInitialized) cheers.stop()
        if (::voice.isInitialized) voice.shutdown()
        super.onDestroy()
    }

    // ---- input ----

    private fun handleSignal(s: Signal) {
        if (s is Signal.Speed) speedKph = s.kph
        apply(detector.onSignal(s, SystemClock.elapsedRealtime()))
        refreshStatus()
    }

    private fun handleCommand(c: Command) {
        when (c) {
            is Command.PickupRequest -> addBubble(c.by, "데리러 와 · ${c.place}", fromCar = false)
            is Command.Cheer -> addBubble(c.from, "🎙 응원 ${if (c.audioUrl != null) "녹음" else "음성"} \"${c.text}\"", fromCar = false)
            Command.Reset -> timeline.removeAllViews()
            else -> Unit
        }
        apply(detector.onCommand(c, SystemClock.elapsedRealtime()))
        refreshStatus()
    }

    // ---- output ----

    private fun apply(effects: List<Effect>) {
        for (e in effects) {
            Log.i(TAG, "effect $e")
            when (e) {
                is Effect.FamilyMessage -> { addBubble("차", e.text, fromCar = true); driveLast.text = "가족에게 보냄: ${e.text}"; link.post("message", e.text) }
                is Effect.Speak -> { voice.say(e.text); link.post("speak", e.text) }
                is Effect.PlayCheer -> cheers.play(e)
                Effect.StopVoice -> { voice.stop(); cheers.stop(); hideCheer() }
                is Effect.ShowScreen -> show(e.screen)
                is Effect.Note -> { showNote(e.text); link.post("note", e.text) }
                is Effect.Banner -> { driveBanner.text = e.text ?: ""; driveBanner.gone(e.text == null) }
            }
        }
        refreshStatus()
    }

    private fun show(screen: Screen) {
        val parkedLike = screen == Screen.HOME || screen == Screen.CHEER
        home.gone(!parkedLike)
        driving.gone(parkedLike)
        pickupCard.gone(screen != Screen.PICKUP_PROMPT)
        if (screen == Screen.PICKUP_PROMPT) {
            val s = detector.snapshot()
            pickupText.text = "${s.pickupPlace ?: "가족"}에서 픽업 요청이 왔어요.\n경유지로 추가할까요?"
            driving.gone(false)
            home.gone(true)
        }
        if (screen != Screen.CHEER) hideCheer()
    }

    private fun showCheer(e: Effect.PlayCheer) {
        cheerTitle.text = "${e.from}의 목소리"
        cheerText.text = e.text
        cheerMeta.text = if (e.audioUrl != null) "녹음 ${clipLength(e.durationMs)} · 정차 중에만 재생 · 출발하면 바로 멈춰요"
        else "녹음 없음 · 문구를 음성으로 읽어요 · 출발하면 바로 멈춰요"
        cheerCard.gone(false)
        startBars()
        link.post("cheer_played", "${e.from}: ${e.text}")
    }

    private fun clipLength(ms: Long): String {
        val s = ((ms + 500) / 1000).coerceAtLeast(0)
        return "%d:%02d".format(s / 60, s % 60)
    }

    private fun hideCheer() {
        cheerCard.gone(true)
        barAnimator?.cancel()
    }

    private fun showNote(text: String) {
        noteBar.text = text
        noteBar.gone(false)
        noteBar.alpha = 1f
        noteBar.animate().cancel()
        noteBar.animate().alpha(0f).setStartDelay(6000).setDuration(800).withEndAction { noteBar.gone(true) }.start()
    }

    private fun refreshStatus() {
        val s = detector.snapshot()
        val moving = s.gear == GearState.DRIVE
        statusPill.text = if (moving) "● 주행 중 · ${speedKph.toInt()} km/h" else "● 정차 중 · 기어 ${gearLabel(s.gear)}"
        statusPill.setTextColor(if (moving) Palette.amber else Palette.green)
        stateValue.text = if (moving) "주행 중 · ${speedKph.toInt()} km/h" else "정차 중 · 기어 ${gearLabel(s.gear)}"
        tripValue.text = s.trip?.let { "${it.destination} · 약 ${it.etaMin}분" } ?: "설정된 목적지 없음"
        pickupValue.text = when (s.pickup) {
            PickupPhase.NONE -> "요청 없음"
            PickupPhase.REQUESTED -> "요청 받음 · 운전자 확인 대기"
            PickupPhase.ACCEPTED -> "경유지로 가는 중 · ${s.pickupPlace}"
            PickupPhase.ARRIVED -> "${s.pickupPlace} 도착 · 탑승 대기"
            PickupPhase.BOARDED -> "뒷좌석 탑승 확인됨"
        }
        cheerValue.text = if (s.pendingCheers == 0) "없음" else "${s.pendingCheers}개 · 멈추면 재생"
    }

    private fun gearLabel(g: GearState) = when (g) {
        GearState.PARK -> "P"; GearState.DRIVE -> "D"; GearState.REVERSE -> "R"; GearState.NEUTRAL -> "N"; GearState.UNKNOWN -> "-"
    }

    private fun addBubble(sender: String, text: String, fromCar: Boolean) {
        val r = row(gap = 14)
        val avatar = label(sender.take(1), 18f, Color.WHITE, bold = true).apply {
            gravity = Gravity.CENTER
            background = rounded(if (fromCar) Palette.amber else Palette.teal, dp(22).toFloat())
        }
        r.addView(avatar, LinearLayout.LayoutParams(dp(44), dp(44)))
        val col = column()
        col.addView(label(text, 22f, if (fromCar) Palette.amberInk else Palette.tealInk).apply {
            background = rounded(if (fromCar) Palette.amberSoft else Palette.tealSoft, dp(16).toFloat())
            setPadding(dp(18), dp(12), dp(18), dp(12))
        }, lp(WRAP_CONTENT))
        col.addView(label("${if (fromCar) "가족석 차량 알림" else sender} · ${clock.format(Date())}", 14f, Palette.muted).apply {
            setPadding(dp(6), dp(4), 0, 0)
        })
        r.addView(col, lp(0, WRAP_CONTENT, 1f))
        timeline.addView(r, lp().apply { bottomMargin = dp(14) })
        timelineScroll.post { timelineScroll.fullScroll(View.FOCUS_DOWN) }
    }

    // ---- layout ----

    private fun buildRoot(): View {
        val root = FrameLayout(this).apply { setBackgroundColor(Palette.bg) }
        home = buildHome()
        driving = buildDriving()
        pickupCard = buildPickupCard()
        cheerCard = buildCheerCard()
        noteBar = label("", 18f, Palette.ink).apply {
            background = rounded(Palette.panel2, dp(14).toFloat(), Palette.line)
            setPadding(dp(22), dp(14), dp(22), dp(14))
            gone(true)
        }
        root.addView(home, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        root.addView(driving, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        root.addView(pickupCard, FrameLayout.LayoutParams(dp(980), WRAP_CONTENT, Gravity.CENTER))
        root.addView(cheerCard, FrameLayout.LayoutParams(dp(860), WRAP_CONTENT, Gravity.CENTER_HORIZONTAL or Gravity.TOP).apply { topMargin = dp(150) })
        root.addView(noteBar, FrameLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL).apply { bottomMargin = dp(36) })
        driving.gone(true)
        pickupCard.gone(true)
        cheerCard.gone(true)
        return root
    }

    private fun buildHome(): View {
        val page = column(padding = 40, gap = 24)
        val header = row()
        val titles = column()
        titles.addView(label("가족석 · 가족방", 16f, Palette.muted))
        titles.addView(label("우리 가족, 오늘도 함께", 34f, bold = true))
        header.addView(titles, lp(0, WRAP_CONTENT, 1f))
        statusPill = label("● 정차 중", 18f, Palette.green).apply {
            background = rounded(Palette.panel2, dp(24).toFloat())
            setPadding(dp(20), dp(10), dp(20), dp(10))
        }
        header.addView(statusPill, lp(WRAP_CONTENT))
        page.addView(header)

        val body = row(gap = 24).apply { gravity = Gravity.TOP }
        val left = column(padding = 26).apply { background = rounded(Palette.panel, dp(22).toFloat(), Palette.line) }
        left.addView(label("오늘의 가족방", 22f, bold = true).apply { setPadding(0, 0, 0, dp(16)) })
        timeline = column()
        timelineScroll = ScrollView(this).apply { addView(timeline) }
        left.addView(timelineScroll, lp(MATCH_PARENT, 0, 1f))
        body.addView(left, lp(0, MATCH_PARENT, 1.55f))

        val right = column(padding = 26, gap = 18).apply { background = rounded(Palette.panel, dp(22).toFloat(), Palette.line) }
        right.addView(label("차량과 가족", 22f, bold = true))
        right.addView(buildMyCar())
        stateValue = statusRow(right, "현재 상태")
        tripValue = statusRow(right, "다음 목적지")
        pickupValue = statusRow(right, "픽업")
        cheerValue = statusRow(right, "도착하면 들을 응원")
        linkValue = label("○ 가족 서버 연결 확인 중", 16f, Palette.muted)
        right.addView(linkValue)
        right.addView(label("주행을 시작하면 화면 대신 음성으로 안내합니다", 15f, Palette.muted))
        body.addView(right, lp(0, MATCH_PARENT, 1f))
        page.addView(body, lp(MATCH_PARENT, 0, 1f))
        return page
    }

    private fun buildMyCar(): View {
        val box = row(gap = 20).apply {
            background = rounded(Palette.panel2, dp(16).toFloat())
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }
        box.addView(CarView(this), LinearLayout.LayoutParams(dp(300), dp(126)))
        val names = column()
        names.addView(label("우리 차", 15f, Palette.muted))
        names.addView(label(MyCar.MODEL, 26f, bold = true))
        names.addView(label(MyCar.COLOR_NAME, 18f, Palette.muted))
        box.addView(names, lp(0, WRAP_CONTENT, 1f))
        return box
    }

    private fun statusRow(parent: LinearLayout, title: String): TextView {
        val box = column(padding = 16).apply { background = rounded(Palette.panel2, dp(16).toFloat()) }
        box.addView(label(title, 15f, Palette.muted))
        val value = label("—", 22f, bold = true)
        box.addView(value)
        parent.addView(box)
        return value
    }

    private fun buildDriving(): View {
        val page = column(padding = 60, gap = 26).apply { gravity = Gravity.CENTER }
        page.addView(label("가족석", 20f, Palette.muted).apply { gravity = Gravity.CENTER })
        page.addView(label("주행 중에는 음성으로만 안내합니다", 36f, bold = true).apply { gravity = Gravity.CENTER })
        driveBanner = label("", 24f, Palette.amberInk).apply {
            gravity = Gravity.CENTER
            background = rounded(Palette.amberSoft, dp(20).toFloat())
            setPadding(dp(30), dp(18), dp(30), dp(18))
            gone(true)
        }
        page.addView(driveBanner, lp(WRAP_CONTENT).apply { gravity = Gravity.CENTER_HORIZONTAL })
        driveLast = label("", 20f, Palette.muted).apply { gravity = Gravity.CENTER }
        page.addView(driveLast)
        return page
    }

    private fun buildPickupCard(): View {
        val card = column(padding = 36, gap = 22).apply { background = rounded(Palette.panel2, dp(28).toFloat(), Palette.amber) }
        card.addView(label("🎙 픽업 요청", 18f, Palette.amber, bold = true))
        pickupText = label("", 30f, bold = true)
        card.addView(pickupText)
        card.addView(label("'응' 또는 '아니'라고 말해 주세요", 18f, Palette.muted))
        val buttons = row(gap = 16)
        buttons.addView(button("추가", Palette.amber, Color.parseColor("#1B1B1B")) { handleCommand(Command.DriverReply(true)) }, lp(0, dp(76), 1f))
        buttons.addView(button("취소", Palette.panel, Palette.ink) { handleCommand(Command.DriverReply(false)) }, lp(0, dp(76), 1f))
        card.addView(buttons)
        return card
    }

    private fun buildCheerCard(): View {
        val card = row(gap = 24).apply {
            background = rounded(Palette.tealSoft, dp(26).toFloat(), Palette.teal)
            setPadding(dp(30), dp(24), dp(30), dp(24))
        }
        card.addView(label("🎙", 40f))
        val text = column()
        cheerTitle = label("", 26f, Palette.tealInk, bold = true)
        cheerText = label("", 24f, Palette.tealInk)
        text.addView(cheerTitle)
        text.addView(cheerText)
        cheerMeta = label("", 15f, Palette.muted)
        text.addView(cheerMeta)
        card.addView(text, lp(0, WRAP_CONTENT, 1f))
        val wave = row(gap = 6)
        repeat(9) {
            val bar = View(this).apply { background = rounded(Palette.teal, dp(4).toFloat()) }
            bars += bar
            wave.addView(bar, LinearLayout.LayoutParams(dp(8), dp(46)))
        }
        card.addView(wave, lp(WRAP_CONTENT, dp(60)))
        return card
    }

    private fun startBars() {
        barAnimator?.cancel()
        barAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 900
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener { a ->
                val t = a.animatedFraction
                bars.forEachIndexed { i, b -> b.scaleY = 0.3f + 0.7f * kotlin.math.abs(kotlin.math.sin((t * 6.28f) + i * 0.7f)) }
            }
            start()
        }
    }

    private fun button(text: String, bg: Int, fg: Int, onClick: () -> Unit) = Button(this).apply {
        this.text = text
        textSize = 24f
        setTextColor(fg)
        isAllCaps = false
        background = rounded(bg, dp(18).toFloat(), Palette.line)
        setOnClickListener { onClick() }
    }
}
