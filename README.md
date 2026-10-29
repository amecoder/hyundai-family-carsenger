# 가족석 (가칭)

> 차가 가족 대화방의 한 구성원이 되어 출발·도착·뒷좌석 탑승을 운전자 대신 가족에게 알리고, 가족의 픽업 요청과 응원 목소리를 운전자가 화면을 만지지 않고 받게 하는 Pleos Connect 앱.

현대자동차그룹 차량용 앱 개발 공모전 출품작입니다. 이 저장소에는 두 가지가 들어 있습니다.

| 폴더 | 내용 |
|---|---|
| `gajokseok-car/` | 에뮬레이터에 설치하는 **차량 앱** (Kotlin, Pleos Vehicle SDK 2.3.2, TextToSpeech SDK 3.3.1) |
| `pleos-scenario/` | **데모 환경**: 시나리오 실행기(Python) + 가족 웹(엄마·아이 폰 역할) + Virtual Console 자동 조작 |
| `apk/` | 바로 설치할 수 있는 차량 앱 APK |

## APK 위치

- `apk/gajokseok-car-0.1-demo.apk` (디버그 서명, 패키지 `dev.gajokseok.car`)

## 테스트 환경

- Pleos Connect Emulator v2.1.0 (Android Automotive 14, API 34), Android Studio 에뮬레이터
- 호스트: Ubuntu 24.04(x86_64) 또는 macOS(Apple Silicon), Android SDK, Python 3.12 이상(실측 3.14) + [uv](https://docs.astral.sh/uv/), Gradle 9.8
- 그래픽: `-gpu host` 권장 (swiftshader는 장시간 실행 중 에뮬레이터가 스스로 종료되는 것을 확인)

## 실행 방법

### 1. 차량 앱만 설치해 보기

```bash
adb install -r --user 10 apk/gajokseok-car-0.1-demo.apk
adb shell am start --user 10 -n dev.gajokseok.car/.MainActivity
```

Pleos 에뮬레이터의 화면 사용자는 10번입니다. Virtual Console에서 기어·2열 문·2열 착석을 바꾸면 앱이 반응합니다.

### 2. 전체 데모 (추천)

```bash
cd pleos-scenario
./start_demo.sh
```

에뮬레이터 부팅, 차량 앱 빌드·설치, 실행기 서버 시작까지 한 번에 합니다. 브라우저에서 http://127.0.0.1:8090 을 열고 시나리오 버튼(9종)을 누르거나, 오른쪽 가족 앱에서 직접 「데리러 와」·「응원 녹음」을 보내 보세요. 자세한 내용은 [`pleos-scenario/README.md`](pleos-scenario/README.md)에 있습니다.

## 필요한 설정

- `ANDROID_HOME` (기본값: 리눅스 `~/Android/Sdk`, macOS `~/Library/Android/sdk`), AVD 이름 `PLEOS_AVD` (기본값 `pleos21`), Gradle 경로 `GRADLE` (기본값 `~/Android/gradle/gradle-9.8.2/bin/gradle`)
- `gajokseok-car/local.properties`에 `sdk.dir=<Android SDK 경로>` 한 줄
- 차량 앱 퍼미션: `CAR_DRIVE`, `CAR_DOORS`, `CAR_SEATS`, `CAR_ENERGY`, `TTS_SERVICE`, `INTERNET` (개발 단계는 선언만으로 동작)
- 가족 앱은 데모에서 PC의 실행기 서버(`10.0.2.2:8090`)를 대역으로 씁니다. 실제 서비스는 Firebase로 연결할 계획입니다.

## 시연 시 주의

- 가족석 앱이 화면 뒤로 가면 Android 14가 앱을 멈춥니다. 시연 중에는 가족석 앱을 앞에 띄워 두세요.
- 기어가 D이면 Pleos가 서드파티 앱 화면을 덮습니다. 가족석은 주행 중에는 음성으로만 안내하도록 설계했습니다.

## 테스트

```bash
cd gajokseok-car && gradle test                                   # 판단 엔진 JUnit
cd pleos-scenario && uv run --no-project --with pytest pytest -q   # 실행기·가족 API
```
