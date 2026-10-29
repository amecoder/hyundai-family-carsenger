plugins { id("com.android.application") }

android {
    namespace = "dev.gajokseok.car"
    compileSdk = 36
    useLibrary("android.car")
    defaultConfig {
        applicationId = "dev.gajokseok.car"
        minSdk = 28
        targetSdk = 34
        versionCode = 1
        versionName = "0.1-demo"
    }
}

dependencies {
    implementation("ai.pleos.playground:Vehicle:2.3.2")
    implementation("ai.pleos.playground:TextToSpeech:3.3.1")
    testImplementation("junit:junit:4.13.2")
}
