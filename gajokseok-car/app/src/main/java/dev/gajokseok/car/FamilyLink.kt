package dev.gajokseok.car

import android.os.Handler
import android.os.Looper
import android.util.Log
import dev.gajokseok.car.core.Command
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

private const val TAG = "GajokLink"

/**
 * Demo stand-in for the family server: talks to the scenario runner on the host PC.
 * 10.0.2.2 is the emulator's alias for the host's 127.0.0.1.
 */
class FamilyLink(
    private val baseUrl: String = "http://10.0.2.2:8090",
    private val onCommand: (Command) -> Unit,
    private val onConnection: (Boolean) -> Unit,
) {
    private val main = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadScheduledExecutor()
    private val sender = Executors.newSingleThreadExecutor()
    /** -1 = just started: ask the hub for its current cursor instead of replaying older commands. */
    @Volatile private var lastSeq = -1L
    @Volatile private var connected: Boolean? = null

    fun start() {
        io.scheduleWithFixedDelay({ poll() }, 0, 500, TimeUnit.MILLISECONDS)
    }

    fun stop() {
        io.shutdownNow()
        sender.shutdownNow()
    }

    /** Fire-and-forget event to the family side (messages, notes, spoken lines). */
    fun post(kind: String, text: String) {
        sender.execute {
            runCatching {
                val body = JSONObject().put("kind", kind).put("text", text).toString().toByteArray()
                val conn = (URL("$baseUrl/api/car/event").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = 2000
                    readTimeout = 2000
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json; charset=utf-8")
                }
                conn.outputStream.use { it.write(body) }
                conn.responseCode
                conn.disconnect()
            }.onFailure { Log.w(TAG, "post $kind failed: ${it.message}") }
        }
    }

    /** Downloads a small file from the relay (driver voice clips); null on failure. */
    fun fetch(url: String): ByteArray? = runCatching {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply { connectTimeout = 2000; readTimeout = 4000 }
        conn.inputStream.use { it.readBytes() }.also { conn.disconnect() }
    }.onFailure { Log.w(TAG, "fetch $url failed: ${it.message}") }.getOrNull()

    private fun poll() {
        try {
            val conn = (URL("$baseUrl/api/car/inbox?after=$lastSeq").openConnection() as HttpURLConnection).apply {
                connectTimeout = 2000
                readTimeout = 2000
            }
            val text = conn.inputStream.bufferedReader().use { it.readText() }
            conn.disconnect()
            setConnected(true)
            val json = JSONObject(text)
            if (lastSeq < 0) {
                lastSeq = json.optLong("cursor", 0)
                return
            }
            // the hub was reset (new scenario) since our last poll: start over from its first command
            if (json.optBoolean("reset_cursor", false)) lastSeq = 0
            val arr = json.getJSONArray("commands")
            for (i in 0 until arr.length()) {
                val o = arr.getJSONObject(i)
                lastSeq = maxOf(lastSeq, o.getLong("seq"))
                parse(o)?.let { cmd -> main.post { onCommand(cmd) } }
            }
        } catch (e: Exception) {
            setConnected(false)
            Log.w(TAG, "poll failed: ${e.message}")
        }
    }

    private fun setConnected(value: Boolean) {
        if (connected == value) return
        connected = value
        main.post { onConnection(value) }
    }

    private fun parse(o: JSONObject): Command? = when (o.getString("type")) {
        "reset" -> Command.Reset
        "set_trip" -> Command.SetTrip(o.getString("destination"), o.getInt("eta_min"), o.getString("driver"), o.getString("child"))
        "set_rest_threshold" -> Command.SetRestThreshold(o.getInt("seconds"))
        "pickup_request" -> Command.PickupRequest(
            o.getString("by"), o.getString("place"), o.getInt("eta_min"),
            lat = o.optDouble("lat").takeUnless { it.isNaN() }, lon = o.optDouble("lon").takeUnless { it.isNaN() },
        )
        "driver_voice" -> Command.DriverVoice("$baseUrl/api/voice/${o.getString("clip")}.pcm", o.optBoolean("fallback_accept", true))
        "driver_reply" -> Command.DriverReply(o.getBoolean("accept"))
        "cheer" -> Command.Cheer(
            o.getString("from"), o.getString("text"),
            audioUrl = o.optString("audio_id").takeIf { !o.isNull("audio_id") && it.isNotEmpty() }?.let { "$baseUrl/api/audio/$it" },
            durationMs = o.optLong("duration_ms", 0),
        )
        else -> { Log.w(TAG, "unknown command ${o.getString("type")}"); null }
    }
}
