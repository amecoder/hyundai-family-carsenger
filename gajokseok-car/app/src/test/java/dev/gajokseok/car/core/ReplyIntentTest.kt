package dev.gajokseok.car.core

import org.junit.Assert.assertEquals
import org.junit.Test

class ReplyIntentTest {
    @Test
    fun yesWords() {
        listOf("응", "추가해 줘", "네 좋아요", "어 그래", "예").forEach { assertEquals(it, true, ReplyIntent.classify(it)) }
    }

    @Test
    fun noWordsWinOverYesWords() {
        listOf("아니", "지금은 안돼", "안 돼", "아니 추가하지 마", "싫어", "추가 안 해", "추가하지 말고 그냥 가", "추가 않을래").forEach { assertEquals(it, false, ReplyIntent.classify(it)) }
    }

    @Test
    fun unrelatedOrEmptySpeechIsUnknown() {
        listOf("", "  ", "음악 틀어 줘", "오늘 날씨").forEach { assertEquals(it, null, ReplyIntent.classify(it)) }
    }
}
