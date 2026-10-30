plugins { id("com.android.application") }

android {
    namespace = "dev.gajokseok.car"
    compileSdk = 36
    defaultConfig {
        applicationId = "dev.gajokseok.car"
        minSdk = 28
        targetSdk = 34
        versionCode = 1
        versionName = "0.2"
    }
    buildTypes {
        // contest reviewers install the APK on the emulator directly: sign release with the debug key
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

dependencies {
    implementation("ai.pleos.playground:Vehicle:2.3.2")
    implementation("ai.pleos.playground:TextToSpeech:3.3.1")
    implementation("ai.pleos.playground:SpeechToText:3.3.1")
    implementation("ai.pleos.playground:NaviHelper:3.0.5")
    testImplementation("junit:junit:4.13.2")
}
