package dev.gajokseok.car.core

private val UNSPEAKABLE = Regex("[^\\p{L}\\p{N}\\s.,?!%]")
private val EXTRA_SPACE = Regex("\\s+")

/** Text for the TTS engine: symbols such as ~ and ○ are dropped so they are not read aloud. */
fun spokenText(text: String): String = text.replace(UNSPEAKABLE, "").replace(EXTRA_SPACE, " ").trim()
