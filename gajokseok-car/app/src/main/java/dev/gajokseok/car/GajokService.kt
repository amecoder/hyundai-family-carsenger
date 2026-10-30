package dev.gajokseok.car

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder

private const val CHANNEL = "gajokseok"

/**
 * Keeps the app process running while the navigation map is in front.
 * Without it Android 14 freezes the backgrounded app and family commands stop arriving.
 */
class GajokService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "현대 패밀리 카신저", NotificationManager.IMPORTANCE_LOW))
        val notification = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("현대 패밀리 카신저")
            .setContentText("가족에게 차 소식을 전하는 중")
            .build()
        // the specialUse type exists from Android 14; older systems take the plain call (minSdk is 28)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(1, notification)
        }
        return START_STICKY
    }
}
