# 가족석 시나리오 실행기 + 데모 환경

시나리오 버튼 하나로 아래 세 가지가 동시에 움직입니다.

1. **Pleos 에뮬레이터의 차량 신호** — Virtual Console을 대신 조작해 기어·속도·문·좌석·충전량을 바꿉니다.
2. **에뮬레이터 안의 가족석 차량 앱** (`gajokseok-car`) — 그 신호를 Vehicle SDK로 받아 탑승 확인·도착·휴식·충전을 판단하고, 화면과 Pleos TTS 음성으로 반응합니다.
3. **엄마 폰(가족 웹) 화면** — 차가 보낸 알림이 실행기 페이지 오른쪽 채팅에 실시간으로 쌓입니다.

## 실행

```bash
cd pleos-scenario
./start_demo.sh            # 에뮬레이터 창을 띄워서 실행
./start_demo.sh --headless # 창 없이 실행
```

### macOS(Apple Silicon)에서 처음 준비할 때 (2026-10-28 실측)

- Pleos 이미지는 x86_64용(`crp-sys-img.xml`)과 **arm64용(`crp-arm64-sys-img.xml`, `crp_car_arm64_emulator.zip` 4.7GB)** 이 따로 있습니다. 애플 실리콘 맥은 arm64용만 돌아갑니다.
- 압축을 풀면 `system.img`가 18.2GB지만 실제 데이터는 6.3GB입니다. 0인 영역을 건너뛰는 희소 파일로 풀어 `~/Library/Android/sdk/system-images/android-34/pleos_car_emulator/arm64-v8a/`에 두면 디스크를 6.4GB만 씁니다.
- AVD `pleos21`: 이미지의 `devices.xml` 사양대로 2560×1440·160dpi·RAM 4GB·`-gpu host`. 에뮬레이터는 데이터 영역을 최소 6GB로 강제하고 그 1.2배(7.4GB)의 디스크 여유를 요구합니다(`-partition-size`로도 줄지 않음).
- 차량 앱 빌드는 Gradle 9.6 이상이 필요합니다(AGP 9.4.1). 스크립트 기본 경로 `~/Android/gradle/gradle-9.8.2`에 둡니다.
- 스크립트는 macOS에서 SDK 경로를 `~/Library/Android/sdk`로 잡고, `setsid` 대신 `python3`의 이중 fork로 에뮬레이터를 분리합니다.
- 부팅 직후 가족석 앱이 지도 앱 뒤로 밀려 있으면 하단 바의 안드로이드 아이콘을 눌러 앞으로 띄웁니다.

스크립트가 하는 일:

1. 에뮬레이터(`pleos21`)가 꺼져 있으면 켜고 부팅을 기다립니다.
2. `adb forward tcp:8088 tcp:8088`로 Virtual Console을 연결합니다.
3. 가족석 차량 앱을 빌드(소스가 바뀌었을 때만)·설치·실행합니다.
4. 실행기 서버를 띄우고 브라우저에서 `http://127.0.0.1:8090`을 엽니다.

끄려면 `Ctrl+C`, 에뮬레이터는 `adb emu kill`.

## 화면 구성

| 영역 | 내용 |
|---|---|
| 왼쪽 | 시나리오 목록 |
| 가운데 | 에뮬레이터 실시간 화면(약 1초 간격 캡처), 차가 말한 문장 자막, 차량 상태, 수동 조작 버튼, 진행 단계 |
| 오른쪽 | 엄마 폰 = 실제로 조작하는 가족 앱(`/family`), 차량 앱 로그(음성 문장·판단 근거) |

## 시나리오

| 시나리오 | 소요 | 보여 주는 것 |
|---|---|---|
| 평일 학원 픽업 | 약 50초 | 출발 → 민지의 픽업 요청 → 음성 승인 → 학원 도착 → 뒷좌석 탑승 확인 → 집 도착·엄마 응원 재생 |
| 출발 전 픽업 요청 · 오른쪽 탑승 | 약 50초 | 주차 중 요청이라 픽업 카드가 화면에 보임 → 오른쪽 뒷문 탑승 확인 → 주차 중 온 응원은 보관 없이 바로 재생 |
| 픽업 거절 (지금은 못 들름) | 약 25초 | 주행 중 요청에 아빠가 "아니" → 차 음성 "가족에게 전할게요" · 가족방 "지금은 들를 수 없어요. 조금만 기다려 줘" |
| 짐만 실음 (오탐 방지) | 약 30초 | 가방만 실으면 "착석 신호 없음 → 알림 안 보냄", 실제로 앉았을 때만 탑승 확인 |
| 주말 장거리 · 휴게소 응원 | 약 60초 | 2시간 연속 운전(시연용 20초) → 휴식 권유 음성 → 휴게소 P에서 민지 응원 재생 |
| 혼자 장거리 (휴식 권유) | 약 40초 | 응원이 없어도 2시간(시연용 20초)이면 "오래 운전하셨어요. 잠시 쉬어 가세요" → 휴게소 정차 알림 |
| 신호 대기 (재생 안 함 확인) | 약 30초 | 속도 0이라도 기어 D면 응원을 재생하지 않고, P에서 재생 |
| 응원이 많은 날 (정차 1회당 3개) | 약 45초 | 주행 중 응원 4개 → 마트 주차 때 3개만 재생 → 남은 1개는 집 주차 때 재생 |
| EV 충전 완료 알림 | 약 10초 | 충전량 80% 도달 시 알림 |

## 가족 앱으로 직접 시연하기

시나리오 버튼 대신 사람이 직접 가족 역할을 할 수 있습니다. 실행기 오른쪽의 엄마 폰이 실제 가족 앱이고, `http://127.0.0.1:8090/family`를 새 창으로 열어도 됩니다(`?as=민지`를 붙이면 민지로 시작).

| 가족 앱 | 차에서 일어나는 일 |
|---|---|
| 글 보내기 | 가족방에만 올라갑니다. 운전 중 메시지 낭독은 기획서에서 뺀 기능이라 차로 보내지 않습니다 |
| 🚗 데리러 와 → 장소 선택 | 차 화면에 "경유지로 추가할까요?" 카드와 음성 질문. 에뮬레이터 창에서 [추가]/[취소]를 직접 누릅니다 |
| 🎙 응원 녹음 (최대 15초) → 보내기 | 주행 중이면 보관했다가 P(주차)에서 **녹음한 목소리 그대로** 재생. 녹음을 못 받으면 문구를 TTS로 읽습니다 |

가운데 **수동 조작** 버튼으로 차를 움직입니다. 예를 들어 픽업 흐름은 이렇게 됩니다.

1. 「처음 상태로」 → 가족 앱(민지)에서 「데리러 와」 → 에뮬레이터에서 [추가]
2. 「출발」(D·40km/h, 「정차」를 누를 때까지 계속 달림) → 「정차」 → 가족방에 "학원 앞에 도착했어요"
3. 「왼쪽 뒷문 열기」 → 「뒷좌석 착석」 → 「왼쪽 뒷문 닫기」 → "뒷좌석 탑승 확인 (민지)"
4. 「출발」 → 가족 앱(엄마)에서 응원 녹음·보내기 → 「정차」 → 차에서 엄마 목소리 재생

주의할 점입니다.

- **가족석 앱을 에뮬레이터 화면 앞에 띄워 두세요.** 안드로이드 14는 화면 뒤로 간 앱을 얼려서(배경 앱 동결) 명령을 받지 못합니다. 지도 등 다른 앱이 앞에 오면 하단의 가족석 아이콘을 누르거나 `adb shell am start --user 10 -n dev.gajokseok.car/.MainActivity`를 실행합니다.
- 녹음은 브라우저 마이크 권한이 필요합니다. `127.0.0.1`은 브라우저가 안전한 주소로 취급해서 https 없이 녹음됩니다. 다른 기기(휴대폰)에서 접속하려면 https가 필요해서 이번 범위에서는 뺐습니다.
- 녹음은 실행기 메모리에만 둡니다(파일당 2MB, 최근 20개). 실행기를 끄면 사라집니다.
- 실행기는 `127.0.0.1`·`localhost`·`10.0.2.2`(에뮬레이터에서 본 PC) 주소로 온 요청만 받고, 다른 웹사이트가 보낸 요청(`Origin`이 다른 POST)은 거부합니다. 브라우저로 아무 사이트나 열어 둔 상태에서 그 사이트가 차를 조작하지 못하게 하려는 것입니다.
- 주행 중에는 시나리오 실행처럼 다른 조작이 막힙니다(「정차」만 가능).

자동 시연·녹화: `record_family_demo.cjs`가 위 흐름을 실제 에뮬레이터로 돌리고 실행기 화면을 녹화합니다(크롬 가짜 마이크라 녹음은 "삐" 소리입니다). 2026-10-28 녹화본은 `docs/plans/submission/가족석_가족앱_시연_초안.mp4`(43초)입니다.

```bash
PW_CORE=<playwright-core 폴더> CHROME=<chromium 실행 파일> node record_family_demo.cjs ~/Android/demo_video/family
```

## 무엇이 실제이고 무엇이 대역인가

| 실제 | 시나리오가 대신 함 | 대역 |
|---|---|---|
| Pleos 에뮬레이터 v2.1.0, 가족석 APK, Vehicle SDK 신호, AAOS 속도, Pleos TTS, 주행 중 Pleos의 화면 가림, 가족 앱의 녹음과 차에서의 재생 | Virtual Console 조작, (시나리오 실행 시) 가족의 픽업 요청·응원과 운전자의 "응" | 가족 서버(실행기가 Firebase 대신), 가족 앱은 PC 브라우저에서 실행(실제 휴대폰 아님), 시나리오 응원(문구를 TTS로 읽음), 내비 경유지·ETA(고정 값) |

## 에뮬레이터에서 알게 된 제약

- **주행 중(D)에는 Pleos가 서드파티 앱 화면을 "주행 중에는 사용할 수 없습니다"로 덮습니다.** `distractionOptimized` 선언이나 설치 출처 지정으로는 풀리지 않았습니다(App Market 승인 영역으로 보임). 가족석은 이때 음성으로만 안내하고, 가족 알림은 계속 보냅니다. 기획서의 "주행 중 음성만" 설계와 같습니다.
- **Virtual Console 속도 명령은 브라우저 세션 신호(`POST /browser/session`, 3초 시한)가 있어야 받아들여집니다.** 실행기가 1초마다 보냅니다.
- **착석 값이 SDK에서 반대로 들어옵니다.** 차량 앱의 `SEAT_OCCUPANCY_INVERTED`가 보정합니다.
- **좌석별 벨트**는 Virtual Console에 조작 기능이 없어 시나리오에 넣지 않았습니다.
- 차량 앱은 에뮬레이터 안에서 `10.0.2.2:8090`(에뮬레이터가 PC를 가리키는 주소)으로 실행기에 접속합니다.
- **에뮬레이터는 `setsid -f`로 실행기와 분리해 띄웁니다.** 실행기의 자식 프로세스로 두면 실행기를 끌 때 에뮬레이터도 같이 꺼졌습니다(2026-10-28 확인).
- **그래픽은 `-gpu host`(인텔 내장 그래픽)를 씁니다.** 종전 `swiftshader_indirect`(CPU로 그래픽을 흉내 냄)는 이 PC에서 에뮬레이터가 2~36분 만에 스스로 충돌했습니다(`/var/log/apport.log`의 signal 11). 같은 조건 30분 반복 실행 비교: swiftshader 19분에 충돌, host 30분·시나리오 50회 충돌 0회(2026-10-28). host는 메모리도 약 7GB → 5GB로 줄었습니다. 다른 PC에서 host가 안 되면 `PLEOS_GPU=swiftshader_indirect ./start_demo.sh`.
- **에뮬레이터는 브라우저 녹음 형식(WebM·Opus)을 그대로 재생합니다**(Android 14). 변환이 필요 없습니다.
- **부팅 직후 Virtual Console은 세션 신호를 받기 전까지 차량 값을 `null`로 줍니다**(`bridge_ready:false`). 실행기 상단 칩의 차량 값은 첫 시나리오를 실행하면 채워집니다.

## 시연 영상 녹화

실행기가 떠 있는 상태에서 아래 명령을 실행하면, 시나리오마다 실행기 화면을 녹화해 `<출력 폴더>/<시나리오 id>.webm`으로 저장합니다(1600×900). 시나리오 id를 뒤에 붙이면 그것만 녹화합니다.

```bash
PW_CORE=<playwright-core 폴더> CHROME=<chromium 실행 파일> node record_demo.cjs ~/Android/demo_video [pickup luggage …]
```

mp4로 바꾸고 하나로 합치는 명령입니다.

```bash
cd ~/Android/demo_video
for f in pickup luggage long_drive red_light ev_charge; do ffmpeg -y -i $f.webm -c:v libx264 -pix_fmt yuv420p -crf 23 $f.mp4; done
printf "file '%s.mp4'\n" pickup luggage long_drive red_light ev_charge > list.txt
ffmpeg -y -f concat -safe 0 -i list.txt -c copy gajokseok_demo_all.mp4
```

2026-10-27 녹화본(5종 합본, 3분 32초)은 `docs/plans/submission/가족석_시연영상_초안.mp4`입니다. 자막·내레이션이 없는 화면 녹화라서 제출용으로는 편집이 필요합니다.

## 구조

| 파일 | 역할 |
|---|---|
| `scenario/vc_client.py` | Virtual Console HTTP API 클라이언트 |
| `scenario/scenarios.py` | 시나리오 정의 (차량 동작 + 가족·운전자 행동), 수동 조작(`MANUAL`) |
| `scenario/runner.py` | 시나리오 실행·중지·상태 |
| `scenario/family.py` | 가족 서버 대역 (차량 앱 명령함 + 가족방 피드 + 녹음 보관함) |
| `scenario/screen.py` | 에뮬레이터 화면 캡처 |
| `scenario/server.py` | 웹 서버 (`/api/scenarios`·`/api/status`·`/api/run/<id>`·`/api/stop`·`/api/car/event`·`/api/car/inbox`·`/api/family/feed`·`/api/screen`, 가족 앱 `/family`·`/api/family/say`·`/api/family/pickup`·`/api/family/cheer`·`/api/audio/<id>`, 수동 조작 `/api/manual/<동작>`) |
| `static/index.html` | 실행기 화면 |
| `static/family.html` | 가족 앱 화면 |
| `../gajokseok-car/` | 가족석 차량 앱 (Kotlin). 판단 엔진은 `core/Detector.kt` |

## 테스트

```bash
uv run --no-project --with pytest pytest -q                 # 실행기 (66개, 브라우저 E2E 1개는 아래 환경변수가 있을 때만)
PW_CORE=<playwright-core 폴더> CHROME=<chromium 실행 파일> uv run --no-project --with pytest pytest -q tests/test_family_e2e.py  # 가족 앱 E2E (크롬 가짜 마이크)
cd ../gajokseok-car && gradle testDebugUnitTest              # 차량 앱 판단 엔진 (20개)
```
