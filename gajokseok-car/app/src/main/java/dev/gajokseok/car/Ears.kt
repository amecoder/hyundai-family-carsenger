package dev.gajokseok.car

import ai.pleos.playground.stt.SpeechToText
import ai.pleos.playground.stt.constant.ErrorType
import ai.pleos.playground.stt.constant.Mode
import ai.pleos.playground.stt.listener.OnInitializeListener
import ai.pleos.playground.stt.listener.ResultListener
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import dev.gajokseok.car.core.ReplyIntent
import java.util.Locale

private const val TAG = "GajokEars"
private const val LISTEN_WINDOW_MS = 8_000L
/** a "응" waits this long in case a refusal follows ("네, 아니야"); a refusal acts at once */
private const val YES_GRACE_MS = 1_200L
private const val BYTES_PER_100_MS = 3_200 // 16 kHz, 16-bit, mono
private const val TRAILING_SILENCE_CHUNKS = 10

/**
 * Pleos SpeechToText in ON_DEVICE mode (no app registration): listens for the driver's "응/아니".
 * [inject] feeds a recorded clip instead of the microphone; the emulator has no host mic, so the demo uses it.
 * All state lives on the main thread; each listening session has an id so late results from an old one are dropped.
 */
class Ears(context: Context, private val onReply: (Boolean, String) -> Unit, private val onHeard: (String) -> Unit) {
    private val main = Handler(Looper.getMainLooper())
    private val stt = SpeechToText(context, Mode.ON_DEVICE)
    @Volatile private var ready = false
    private var session = 0
    private var listening = false
    private var micOpen = false
    private var pendingYes: Runnable? = null
    private val giveUp = Runnable { finish(session, null, "") }

    private val listener = object : ResultListener {
        override fun onReady() = Unit
        override fun onStartedRecognition() = Unit
        override fun onUpdatedEpdData(on: Long, off: Long) = Unit
        override fun onUpdatedRms(rms: Double) = Unit
        override fun onEndedRecognition() = Unit
        override fun onError(errorType: ErrorType) { Log.w(TAG, "stt error $errorType") }
        override fun onUpdated(stt: String, completed: Boolean) {
            val heardIn = session
            main.post { heard(heardIn, stt, completed) }
        }
    }

    init {
        runCatching {
            stt.initialize(object : OnInitializeListener {
                override fun onSuccess() {
                    stt.addListener(listener)
                    runCatching { stt.setLocale(Locale.KOREA) }
                    ready = true
                    Log.i(TAG, "pleos stt ready")
                }
                override fun onFailure(errorType: ErrorType) { Log.e(TAG, "pleos stt init failed: $errorType") }
            })
        }.onFailure { Log.e(TAG, "pleos stt unavailable", it) }
    }

    /** Opens the microphone for one answer; gives up silently after the window. A clip already being fed keeps its session. */
    fun listen() {
        if (!ready) return
        if (!listening) startSession()
        if (!micOpen) {
            micOpen = true
            runCatching { stt.request() }.onFailure { Log.w(TAG, "request failed", it) }
        }
    }

    /** Feeds 16 kHz mono PCM as if the driver had spoken it. Returns false when recognition is not available. */
    fun inject(pcm: ByteArray): Boolean {
        if (!ready) return false
        if (!listening) startSession()
        Thread {
            runCatching {
                pcm.asList().chunked(BYTES_PER_100_MS).forEach { stt.sendAudio(it.toByteArray()); Thread.sleep(100L) }
                // trailing silence lets the end-point detector close the utterance
                repeat(TRAILING_SILENCE_CHUNKS) { stt.sendAudio(ByteArray(BYTES_PER_100_MS)); Thread.sleep(100L) }
                stt.completeAudioSend()
            }.onFailure { Log.w(TAG, "inject failed", it) }
        }.start()
        return true
    }

    fun cancel() = finish(session, null, "")

    private fun startSession() {
        session += 1
        listening = true
        main.removeCallbacks(giveUp)
        main.postDelayed(giveUp, LISTEN_WINDOW_MS)
    }

    private fun heard(inSession: Int, text: String, completed: Boolean) {
        if (inSession != session || !listening || text.isBlank()) return
        Log.i(TAG, "heard \"$text\" final=$completed")
        onHeard(text)
        when (ReplyIntent.classify(text)) {
            false -> finish(inSession, false, text)
            true -> if (pendingYes == null) {
                pendingYes = Runnable { finish(inSession, true, text) }.also { main.postDelayed(it, YES_GRACE_MS) }
            }
            null -> Unit
        }
    }

    private fun finish(inSession: Int, answer: Boolean?, text: String) {
        if (inSession != session || !listening) return
        listening = false
        session += 1
        pendingYes?.let { main.removeCallbacks(it) }
        pendingYes = null
        main.removeCallbacks(giveUp)
        if (micOpen) runCatching { stt.stop() }
        micOpen = false
        if (answer != null) onReply(answer, text)
    }

    fun shutdown() {
        cancel()
        runCatching { stt.removeListener(listener); stt.release() }
    }
}
