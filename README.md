# 현대 패밀리 카신저

> 차가 가족 대화방의 한 구성원이 되어 출발·도착·뒷좌석 탑승을 운전자 대신 가족에게 알리고, 가족의 픽업 요청과 응원 목소리를 운전자가 화면을 만지지 않고 받게 하는 Pleos Connect 앱.

## 시연 영상 (46초, 소리 포함)

[![시연 영상 미리보기 — 누르면 소리 있는 영상이 열립니다](docs/demo/carsenger_demo_preview.gif)](https://amecoder.github.io/hyundai-family-carsenger/)

**▶ [소리 있는 영상 보기](https://amecoder.github.io/hyundai-family-carsenger/)** — 위 미리보기는 소리가 없습니다. 브라우저에서 바로 재생됩니다(GitHub Pages). 파일로 받으려면 [`docs/demo/carsenger_demo.mp4`](docs/demo/carsenger_demo.mp4).

Pleos 에뮬레이터(가운데)와 가족 웹(오른쪽, 엄마·민지 폰 역할)을 함께 녹화했습니다. 소리는 에뮬레이터의 차량 음성 안내와 응원 재생입니다.

1. 민지가 가족 웹에서 「데리러 와」(○○수학학원 앞)를 보내면, 차가 "경유지로 추가할까요?"라고 묻습니다.
2. 운전자가 "응, 추가해 줘"라고 답하면 음성 인식으로 승인되고, 내비에 경로가 잡히며, 가족방에 "가는 중"이 전해집니다.
3. 학원에 도착하면 차가 도착을 알리고, 뒷좌석 문·착석으로 민지의 탑승을 확인해 가족에게 알립니다.
4. 집으로 가는 동안 엄마가 응원을 녹음해 보내면, 주행 중에는 기다렸다가 집에 도착해 정차했을 때 차에서 재생합니다.

> 녹화 조건: 운전자 목소리와 엄마의 녹음은 공개 TTS로 만든 음성을 마이크 대신 넣었습니다. 차량 신호는 Virtual Console을 자동으로 조작했습니다. 녹화 스크립트는 `pleos-scenario/record_family_demo.cjs`입니다.

## 저장소 구성

현대자동차그룹 차량용 앱 개발 공모전 출품작입니다(팀 nemo). 이 저장소에는 두 가지가 들어 있습니다.

| 폴더 | 내용 |
|---|---|
| `gajokseok-car/` | 에뮬레이터에 설치하는 **차량 앱** (Kotlin, Pleos Vehicle SDK 2.3.2, TextToSpeech 3.3.1, SpeechToText 3.3.1, NaviHelper 3.0.5) |
| `pleos-scenario/` | **데모 환경**: 시나리오 실행기(Python) + 가족 웹(엄마·아이 폰 역할) + Virtual Console 자동 조작 |
| `apk/` | 바로 설치할 수 있는 차량 앱 APK |

폴더·패키지 이름의 `gajokseok`은 개발 중 가칭(가족석)이며, 앱에 표시되는 이름은 「현대 패밀리 카신저」입니다.

## 주요 기능

- **차가 먼저 알림**: 출발, 도착, 뒷좌석 탑승, 장시간 운전 휴식, 충전 상태를 가족 대화방에 보냅니다.
- **픽업 요청을 목소리로 처리**: 가족이 「데리러 와」를 보내면 차가 음성으로 묻고, 운전자가 "응, 추가해 줘" / "아니, 지금은 안 돼"로 답합니다(Pleos 음성 인식). 승인하면 내비에 픽업 장소가 경로 또는 경유지로 들어갑니다(NaviHelper).
- **응원 녹음**: 가족이 녹음한 응원을 차가 정차했을 때 재생합니다. 주행 중(D)에는 화면 대신 음성으로만 안내합니다.

## APK 위치

- `apk/nemo_현대패밀리카신저_release.apk` (release 빌드, 버전 0.2, 패키지 `dev.gajokseok.car`. 심사용 설치를 위해 디버그 키로 서명)

## 테스트 환경

- Pleos Connect Emulator v2.1.0 (Android Automotive 14, API 34), Android Studio 에뮬레이터
- 호스트: Ubuntu 24.04(x86_64) 또는 macOS(Apple Silicon), Android SDK, Python 3.12 이상(실측 3.14) + [uv](https://docs.astral.sh/uv/), Gradle 9.8
- 그래픽: `-gpu host` 권장 (swiftshader는 장시간 실행 중 에뮬레이터가 스스로 종료되는 것을 확인)

## 실행 방법

### 1. 차량 앱만 설치해 보기

```bash
adb install -r --user 10 "apk/nemo_현대패밀리카신저_release.apk"
adb shell am start --user 10 -n dev.gajokseok.car/.MainActivity
```

Pleos 에뮬레이터의 화면 사용자는 10번입니다. Virtual Console에서 기어·2열 문·2열 착석을 바꾸면 앱이 반응합니다.

### 2. 전체 데모 (추천)

```bash
cd pleos-scenario
./start_demo.sh
```

에뮬레이터 부팅, 차량 앱 빌드·설치, 실행기 서버 시작까지 한 번에 합니다. 브라우저에서 http://127.0.0.1:8090 을 열고 시나리오 버튼을 누르거나, 오른쪽 가족 앱에서 직접 「데리러 와」·「응원 녹음」을 보내 보세요. 자세한 내용은 [`pleos-scenario/README.md`](pleos-scenario/README.md)에 있습니다.

## 필요한 설정

- `ANDROID_HOME` (기본값: 리눅스 `~/Android/Sdk`, macOS `~/Library/Android/sdk`), AVD 이름 `PLEOS_AVD` (기본값 `pleos21`), Gradle 경로 `GRADLE` (기본값 `~/Android/gradle/gradle-9.8.2/bin/gradle`)
- `gajokseok-car/local.properties`에 `sdk.dir=<Android SDK 경로>` 한 줄
- 차량 앱 퍼미션: `CAR_DRIVE`, `CAR_DOORS`, `CAR_SEATS`, `CAR_ENERGY`, `TTS_SERVICE`, `STT_SERVICE`, `NAVI_ROUTE`, `NAVI_ROUTE_SEARCH`, `RECORD_AUDIO`, `FOREGROUND_SERVICE`(`SPECIAL_USE`), `INTERNET` (개발 단계는 선언만으로 동작)
- 데모용 음성 파일(운전자 답변·응원 녹음)은 공개 TTS로 만든 것이며 저장소에 넣지 않았습니다. `PLEOS_VOICE_DIR`(기본 `~/Android/voice`)에 `driver_yes.pcm`, `driver_no.pcm`(16kHz 16bit 모노)을 두면 시나리오가 운전자 목소리로 음성 인식에 넣습니다. 없으면 6초 뒤 「음성 파일·인식 사용 불가 → 시연 응답 적용」을 표시하고 시나리오에 정해 둔 답으로 처리합니다. `cheer_mom.wav`는 시연 녹화 스크립트(`record_family_demo.cjs`)가 가족의 응원 녹음으로 씁니다.
- 가족 앱은 데모에서 PC의 실행기 서버(`10.0.2.2:8090`)를 대역으로 씁니다. 실제 서비스는 Firebase로 연결할 계획입니다.

## 시연 시 주의

- 앱은 포그라운드 서비스로 동작해서 내비가 화면 앞에 있어도 가족 메시지와 음성 안내를 처리합니다.
- 경유지 추가는 내비 앱이 화면 앞에 있어야 동작합니다(NaviHelper 조건). 앱이 승인 직후 내비를 앞으로 띄웁니다.
- 기어가 D이면 Pleos가 서드파티 앱 화면을 덮습니다. 이 앱은 주행 중에는 음성으로만 안내하도록 설계했습니다.

## 테스트

```bash
cd gajokseok-car && gradle test                                   # 판단 엔진·음성 답변 분류 JUnit
cd pleos-scenario && uv run --no-project --with pytest pytest -q   # 실행기·가족 API
```
