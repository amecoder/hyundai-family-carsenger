package dev.gajokseok.car

import ai.pleos.playground.navi.constants.NaviErrorCode
import ai.pleos.playground.navi.constants.NaviMode
import ai.pleos.playground.navi.constants.NavigationStatus
import ai.pleos.playground.navi.constants.WaypointIndex
import ai.pleos.playground.navi.data.RequestWaypointInfo
import ai.pleos.playground.navi.data.RouteInfo
import ai.pleos.playground.navi.data.RouteStartInfo
import ai.pleos.playground.navi.data.RouteStateInfo
import ai.pleos.playground.navi.data.WaypointChangedInfo
import ai.pleos.playground.navi.helper.NaviHelper
import ai.pleos.playground.navi.helper.listener.NaviHelperEventListener
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log

private const val TAG = "GajokNavi"
/** the navigation app drops requests unless its map is on screen (measured 2026-10-29), so we give it a moment */
private const val SHOW_NAVI_DELAY_MS = 1_500L
/** route events within this window answer our request; later ones are the map recalculating on its own */
private const val ANSWER_WINDOW_MS = 15_000L

/**
 * Puts an accepted pickup place into the car's navigation with NaviHelper.
 * Coordinates alone are enough (no poiId); while guiding it becomes waypoint 1, otherwise the destination.
 */
class NaviLink(private val context: Context, private val onNote: (String) -> Unit) {
    private val main = Handler(Looper.getMainLooper())
    private val navi = NaviHelper(context.applicationContext)
    @Volatile private var connected = false
    /** null = not known yet; picking requestRoute while unsure could replace a route the driver is following */
    @Volatile private var guiding: Boolean? = null
    @Volatile private var askedAtMs = 0L

    private val listener = object : NaviHelperEventListener {
        override fun onRouteStateInfo(routeStateInfo: RouteStateInfo) {
            guiding = routeStateInfo.naviMode == NaviMode.ROUTE_GUIDING
        }
        override fun onNavigationStatus(navigationStatus: NavigationStatus) {
            guiding = navigationStatus == NavigationStatus.ROUTE_DRIVE
        }
        override fun onWaypointChanged(waypointChangedInfo: WaypointChangedInfo) {
            waypointChangedInfo.routeStartInfo?.let { answer("내비 경유지 추가됨", it) }
        }
        override fun onRouteStarted(routeStartInfo: RouteStartInfo) = answer("내비 경로 안내 시작", routeStartInfo)
        override fun onError(errorCode: NaviErrorCode) = report("내비 오류: $errorCode")
    }

    init {
        runCatching {
            navi.initialize(
                onConnected = {
                    connected = true
                    navi.addListener(listener)
                    navi.getRouteStateInfo()
                    Log.i(TAG, "navi helper connected")
                },
                onFailed = { Log.e(TAG, "navi helper failed", it) },
            )
        }.onFailure { Log.e(TAG, "navi helper unavailable", it) }
    }

    fun addPickup(place: String, lat: Double, lon: Double) {
        if (!connected) return report("내비 연결 전이라 경유지를 넣지 못했어요")
        showNavigation()
        main.postDelayed({
            runCatching { navi.getRouteStateInfo() }
            main.postDelayed({ send(place, lat, lon) }, SHOW_NAVI_DELAY_MS)
        }, SHOW_NAVI_DELAY_MS)
    }

    private fun send(place: String, lat: Double, lon: Double) {
        val state = guiding ?: return report("내비 안내 상태를 알 수 없어 경유지를 넣지 않았어요")
        run {
            runCatching {
                if (state) {
                    navi.addWaypoint(RequestWaypointInfo(latitude = lat, longitude = lon, poiName = place, waypointIndex = WaypointIndex.FIRST, poiId = "", address = "", poiSubId = ""))
                } else {
                    navi.requestRoute(RouteInfo(latitude = lat, longitude = lon, poiName = place, poiId = "", address = "", poiSubId = ""))
                }
                askedAtMs = SystemClock.elapsedRealtime()
                Log.i(TAG, "pickup sent to navi: $place ($lat,$lon) guiding=$state")
            }.onFailure { report("내비 요청 실패: ${it.message}") }
        }
    }

    /** Scenario reset: drop the demo route and waypoints so the next run starts from free driving. */
    fun clear() {
        if (!connected) return
        runCatching { navi.removeWaypoint(WaypointIndex.ALL); navi.cancelRoute() }.onFailure { Log.w(TAG, "clear failed", it) }
        // the map drops requests while it is behind us, so the route may still be there: ask again before the next pickup
        guiding = null
    }

    private fun showNavigation() {
        runCatching {
            val intent = Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_MAPS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
        }.onFailure { Log.w(TAG, "could not bring the map to front", it) }
    }

    private fun answer(prefix: String, info: RouteStartInfo) {
        if (SystemClock.elapsedRealtime() - askedAtMs > ANSWER_WINDOW_MS) return
        askedAtMs = 0L
        report("$prefix: ${info.name} · 약 ${(info.duration + 59) / 60}분 · ${"%.1f".format(info.distance / 1000.0)}km")
    }

    private fun report(text: String) {
        Log.i(TAG, text)
        main.post { onNote(text) }
    }

    fun release() = runCatching { navi.removeListener(listener); navi.release() }
}
