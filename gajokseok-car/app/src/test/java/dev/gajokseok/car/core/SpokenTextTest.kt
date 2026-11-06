package dev.gajokseok.car.core

import org.junit.Assert.assertEquals
import org.junit.Test

class SpokenTextTest {
    @Test
    fun removesTildeFromFamilyLine() {
        assertEquals("조심히 와 저녁 준비해 둘게", spokenText("조심히 와~ 저녁 준비해 둘게"))
    }

    @Test
    fun removesPlaceholderCircles() {
        assertEquals("졸음 신호가 보여요. 졸음쉼터에 들를까요?", spokenText("졸음 신호가 보여요. ○○ 졸음쉼터에 들를까요?"))
    }

    @Test
    fun keepsPunctuationAndNumbers() {
        assertEquals("충전 80% 완료, 출발 가능", spokenText("충전 80% 완료, 출발 가능"))
        assertEquals("민지가 역 2번 출구에서", spokenText("민지가 ○○역 2번 출구에서"))
    }

    @Test
    fun leavesPlainTextUnchanged() {
        assertEquals("오래 운전하셨어요. 잠시 쉬어 가세요.", spokenText("오래 운전하셨어요. 잠시 쉬어 가세요."))
    }
}
