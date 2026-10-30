package dev.gajokseok.car.core

/** Turns the driver's recognised speech into accept (true), decline (false) or unknown (null). */
object ReplyIntent {
    // checked on the text with spaces removed; refusals win ("아니 추가하지 마")
    private val noParts = listOf("아니", "안돼", "안되", "안해", "않", "싫어", "하지마", "말고", "말아", "됐어")
    private val yesParts = listOf("추가", "그래", "좋아", "오케이")
    // short answers only count as whole words ("틀어" must not read as "어")
    private val yesWords = setOf("응", "웅", "엉", "어", "네", "예")

    fun classify(text: String): Boolean? {
        val compact = text.replace(Regex("\\s+"), "")
        if (compact.isEmpty()) return null
        if (noParts.any { it in compact }) return false
        val words = text.split(Regex("[\\s,.!?~]+")).filter { it.isNotEmpty() }
        if (yesParts.any { it in compact } || words.any { it in yesWords }) return true
        return null
    }
}
