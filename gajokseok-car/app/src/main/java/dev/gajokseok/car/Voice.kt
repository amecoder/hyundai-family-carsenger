package dev.gajokseok.car

import ai.pleos.playground.tts.TextToSpeech
import ai.pleos.playground.tts.constant.ErrorType
import ai.pleos.playground.tts.constant.Mode
import ai.pleos.playground.tts.listener.EventListener
import ai.pleos.playground.tts.listener.OnInitializeListener
import android.content.Context
import android.media.AudioAttributes
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.util.Locale

private const val TAG = "GajokVoice"

/**
 * Pleos TextToSpeech SDK in ON_DEVICE mode (no app registration needed).
 * Recorded family cheers are played by CheerPlayer; this reads a cheer's text only when there is no playable clip.
 */
class Voice(context: Context, private val onReady: (Boolean, String?) -> Unit) {
    private val tts = TextToSpeech(context, Mode.ON_DEVICE)
    @Volatile var ready = false
        private set
    private val main = Handler(Looper.getMainLooper())
    // speaking/afterSpeech are only touched on the main thread; TTS callbacks hop over first
    private var speaking = false
    private var afterSpeech: (() -> Unit)? = null

    private val events = object : EventListener {
        override fun onStart() = Unit
        override fun onReady() = Unit
        override fun onUpdatedRms(rms: Double) = Unit
        override fun onDone() { main.post(::finished) }
        override fun onStop() { main.post(::finished) }
        override fun onError(errorType: ErrorType) { main.post(::finished) }
    }

    init {
        runCatching {
            tts.initialize(object : OnInitializeListener {
                override fun onSuccess() {
                    runCatching {
                        tts.setLocale(Locale.KOREA)
                        // ducking guidance audio, as in the plan (AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK style usage)
                        tts.setAudioAttributes(
                            AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                                .build(),
                        )
                    }.onFailure { Log.w(TAG, "tts config failed", it) }
                    runCatching { tts.addEventListener(events) }
                    ready = true
                    Log.i(TAG, "pleos tts ready")
                    onReady(true, null)
                }

                override fun onFailure(errorType: ErrorType) {
                    Log.e(TAG, "pleos tts init failed: $errorType")
                    onReady(false, errorType.toString())
                }
            })
        }.onFailure {
            Log.e(TAG, "pleos tts unavailable", it)
            onReady(false, it.message)
        }
    }

    fun say(text: String) = speak(text)

    fun cheer(text: String) = speak(text)

    /** Runs [action] once the current sentence has been spoken (right away when nothing is playing). */
    fun afterSpeech(action: () -> Unit) {
        if (speaking) afterSpeech = action else main.post(action)
    }

    private fun finished() {
        speaking = false
        val next = afterSpeech ?: return
        afterSpeech = null
        next()
    }

    private fun speak(text: String) {
        if (!ready) return
        speaking = true
        runCatching { tts.speak(text, false) }.onFailure { speaking = false; Log.e(TAG, "speak failed", it) }
    }

    fun stop() {
        afterSpeech = null
        if (ready) runCatching { tts.stop() }
    }

    fun shutdown() = runCatching { tts.release() }
}
