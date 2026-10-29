#!/usr/bin/env bash
# One-shot launcher: boot the Pleos emulator (if needed), forward Virtual Console, start the scenario runner, open the browser.
# Usage: ./start_demo.sh [--headless]
set -euo pipefail

# Android Studio's default SDK location differs per OS.
if [[ "$(uname)" == "Darwin" ]]; then DEFAULT_SDK="$HOME/Library/Android/sdk"; else DEFAULT_SDK="$HOME/Android/Sdk"; fi
# Exported so the runner's screen capture (scenario/screen.py) uses the same SDK.
export ANDROID_HOME="${ANDROID_HOME:-$DEFAULT_SDK}"
AVD="${PLEOS_AVD:-pleos21}"
PORT="${RUNNER_PORT:-8090}"
# host = the Intel iGPU via Mesa. swiftshader_indirect (software) crashed the emulator with SIGSEGV
# after 2-36 min on this PC (2026-10-28); host ran 30 min / 50 scenarios with no crash. Override with PLEOS_GPU.
GPU="${PLEOS_GPU:-host}"
ADB="$ANDROID_HOME/platform-tools/adb"
EMULATOR="$ANDROID_HOME/emulator/emulator"
HERE="$(cd "$(dirname "$0")" && pwd)"
WINDOW_FLAG=()
[[ "${1:-}" == "--headless" ]] && WINDOW_FLAG=(-no-window)

for bin in "$ADB" "$EMULATOR"; do
  [[ -x "$bin" ]] || { echo "찾을 수 없음: $bin (ANDROID_HOME 확인)" >&2; exit 1; }
done

if ! "$ADB" devices | grep -q '^emulator-.*device$'; then
  echo "에뮬레이터 부팅 중… (처음에는 1~2분 걸릴 수 있습니다)"
  # Detach the emulator so it is not a child of this script: stopping the launcher
  # (which kills its whole process tree) must leave the emulator running.
  # Linux: setsid -f. macOS has no setsid command, and a background job (even after os.setsid) stays a
  # child of this script and dies with its process tree (2026-10-28). So python3 does what setsid -f does:
  # fork, let the parent exit (the emulator is reparented to launchd), then setsid + exec in the child.
  mkdir -p "$HOME/Android"
  # ${A[@]+...} form: macOS /bin/bash 3.2 treats an empty array as unbound under set -u.
  EMU_CMD=(nohup "$EMULATOR" -avd "$AVD" ${WINDOW_FLAG[@]+"${WINDOW_FLAG[@]}"} -no-snapshot -no-boot-anim -gpu "$GPU")
  if command -v setsid >/dev/null; then
    setsid -f "${EMU_CMD[@]}" > "$HOME/Android/emu.log" 2>&1 < /dev/null
  else
    python3 -c 'import os, sys; os.fork() and os._exit(0); os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' \
      "${EMU_CMD[@]}" > "$HOME/Android/emu.log" 2>&1 < /dev/null
  fi
fi

"$ADB" wait-for-device
for _ in $(seq 1 120); do
  [[ "$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]] && break
  sleep 3
done
[[ "$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]] || { echo "부팅 시간 초과 — ~/Android/emu.log 확인" >&2; exit 1; }

echo "Virtual Console 준비 확인 중…"
"$ADB" forward tcp:8088 tcp:8088 >/dev/null
for _ in $(seq 1 60); do
  curl -sf http://127.0.0.1:8088/vehicle/state >/dev/null && break
  sleep 2
done
curl -sf http://127.0.0.1:8088/vehicle/state >/dev/null || { echo "Virtual Console이 응답하지 않습니다" >&2; exit 1; }

CAR_DIR="$HERE/../gajokseok-car"
APK="$CAR_DIR/app/build/outputs/apk/debug/app-debug.apk"
GRADLE="${GRADLE:-$HOME/Android/gradle/gradle-9.8.2/bin/gradle}"
if [[ ! -f "$APK" || -n "$(find "$CAR_DIR/app/src" "$CAR_DIR/app/build.gradle.kts" -newer "$APK" -type f -print -quit)" ]]; then
  [[ -x "$GRADLE" ]] || { echo "Gradle을 찾을 수 없음: $GRADLE (GRADLE 환경변수로 지정)" >&2; exit 1; }
  echo "가족석 차량 앱 빌드 중… (처음에는 몇 분 걸립니다)"
  (cd "$CAR_DIR" && ANDROID_HOME="$ANDROID_HOME" "$GRADLE" --no-daemon -q assembleDebug)
fi
echo "가족석 차량 앱 설치·실행"
"$ADB" install -r -g "$APK" >/dev/null
"$ADB" shell pm grant dev.gajokseok.car android.car.permission.CAR_SPEED 2>/dev/null || true
"$ADB" shell am start -n dev.gajokseok.car/.MainActivity >/dev/null

URL="http://127.0.0.1:$PORT/"
if [[ -z "${NO_BROWSER:-}" ]]; then
  OPENER=xdg-open
  [[ "$(uname)" == "Darwin" ]] && OPENER=open
  ( sleep 1.5; command -v "$OPENER" >/dev/null && "$OPENER" "$URL" >/dev/null 2>&1 || echo "브라우저에서 $URL 을 여세요" ) &
fi
echo "실행기 시작: $URL  (끄려면 Ctrl+C)"
cd "$HERE"
exec python3 -m scenario.server --port "$PORT"
