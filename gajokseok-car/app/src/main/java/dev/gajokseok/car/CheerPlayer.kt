package dev.gajokseok.car

import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Handler
import android.os.Looper
import android.util.Log
import dev.gajokseok.car.core.Effect

private const val TAG = "GajokCheer"

/** If a clip has not started by then (server stalled, network gone), read the text instead so the queue keeps moving. */
private const val PREPARE_TIMEOUT_MS = 10_000L

/**
 * Plays family cheers one after another: the recorded clip when there is one, otherwise (or when the clip fails)
 * the cheer text through TTS. onStart fires as each cheer begins; onIdle once the queue is empty so the cheer card can close.
 */
class CheerPlayer(
    private val voice: Voice,
    private val onStart: (Effect.PlayCheer) -> Unit,
    private val onIdle: () -> Unit,
) {
    private val main = Handler(Looper.getMainLooper())
    private val queue = ArrayDeque<Effect.PlayCheer>()
    private var player: MediaPlayer? = null
    private var busy = false

    fun play(cheer: Effect.PlayCheer) {
        queue.addLast(cheer)
        if (!busy) next()
    }

    fun stop() {
        queue.clear()
        main.removeCallbacksAndMessages(null)
        release()
        busy = false
    }

    private fun next() {
        release()
        val cheer = queue.removeFirstOrNull()
        if (cheer == null) {
            busy = false
            onIdle()
            return
        }
        busy = true
        onStart(cheer)
        val url = cheer.audioUrl
        if (url == null) speakInstead(cheer, "no recording") else playClip(cheer, url)
    }

    private fun playClip(cheer: Effect.PlayCheer, url: String) {
        val mp = MediaPlayer()
        player = mp
        val watchdog = Runnable { if (player === mp) speakInstead(cheer, "prepare timed out") }
        main.postDelayed(watchdog, PREPARE_TIMEOUT_MS)
        runCatching {
            mp.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            mp.setDataSource(url)
            mp.setOnPreparedListener { main.removeCallbacks(watchdog); it.start(); Log.i(TAG, "playing ${cheer.from} clip $url") }
            mp.setOnCompletionListener { Log.i(TAG, "clip done"); next() }
            mp.setOnErrorListener { _, what, extra -> main.removeCallbacks(watchdog); speakInstead(cheer, "media error $what/$extra"); true }
            mp.prepareAsync()
        }.onFailure { main.removeCallbacks(watchdog); speakInstead(cheer, it.message ?: it.toString()) }
    }

    private fun speakInstead(cheer: Effect.PlayCheer, reason: String) {
        release()
        Log.w(TAG, "cheer by TTS (${cheer.from}): $reason")
        voice.cheer(cheer.text)
        // TTS gives no completion callback here, so allow a reading time that scales with the text
        main.postDelayed({ next() }, 2500L + cheer.text.length * 180L)
    }

    private fun release() {
        player?.let { runCatching { it.reset(); it.release() } }
        player = null
    }
}
