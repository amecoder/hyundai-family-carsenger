// Records the hands-on family app demo against the real emulator: family app (iframe) + manual controls + taps on the car screen.
// Usage: PW_CORE=<playwright-core dir> CHROME=<chromium binary> [ADB=<adb>] [PLEOS_VOICE_DIR=<dir>] node record_family_demo.cjs <out dir>
// Needs ./start_demo.sh running. The family's cheer is cheer_mom.wav from the voice folder fed as Chrome's microphone;
// the emulator's sound is recorded from the PC's default audio output and muxed into family_demo.mp4 (needs parecord + ffmpeg).
const { execFileSync, spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const { chromium } = require(process.env.PW_CORE);

const BASE = "http://127.0.0.1:8090";
const VOICE_DIR = process.env.PLEOS_VOICE_DIR || `${process.env.HOME}/Android/voice`;
const ADB = process.env.ADB || `${process.env.HOME}/Android/Sdk/platform-tools/adb`;
const adb = (...args) => execFileSync(ADB, args, { encoding: "utf8" });

// the car app is frozen by Android while it is in the background, so keep it in front
const carAppToFront = () => adb("shell", "am", "start", "--user", "10", "-n", "dev.gajokseok.car/.MainActivity");

// the emulator plays through the PC's default output; its monitor source carries the car's voice and the cheer
function startAudioCapture(file) {
  const sink = execFileSync("pactl", ["get-default-sink"], { encoding: "utf8" }).trim();
  return spawn("parecord", ["-d", `${sink}.monitor`, "--file-format=wav", file], { stdio: "ignore" });
}

(async () => {
  const out = process.argv[2];
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    executablePath: process.env.CHROME,
    args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", `--use-file-for-fake-audio-capture=${path.join(VOICE_DIR, "cheer_mom.wav")}`],
  });
  const context = await browser.newContext({ viewport: { width: 1600, height: 900 }, recordVideo: { dir: out, size: { width: 1600, height: 900 } } });
  await context.grantPermissions(["microphone"], { origin: BASE });
  const page = await context.newPage();
  const videoStart = Date.now();
  const audioFile = path.join(out, "car_audio.wav");
  const audio = startAudioCapture(audioFile);
  const audioStart = Date.now();
  const phone = page.frameLocator("iframe.phone");
  const chat = text => phone.locator(".chat").getByText(text).first().waitFor({ timeout: 30000 });
  const manual = async (action, settleMs = 0) => {
    await page.click(`#manual button[data-a="${action}"]`);
    await page.waitForFunction(() => !document.querySelector("#state").textContent.startsWith("실행 중"), null, { timeout: 30000 });
    await page.waitForTimeout(settleMs);
  };
  const step = name => console.log(new Date().toTimeString().slice(0, 8), name);

  await page.goto(BASE + "/");
  await phone.locator("#link:has-text('연결됨')").waitFor();
  carAppToFront();

  step("reset");
  await manual("reset", 2500);

  step("민지 requests a pickup");
  await phone.locator("#who button[data-s='민지']").click();
  await phone.locator("#pickBtn").click();
  await phone.locator("#places button", { hasText: "○○수학학원 앞" }).click();
  await page.waitForTimeout(3500);
  step("driver answers out loud: 응, 추가해 줘");
  await page.click('#voice button[data-clip="driver_yes"]');
  await chat("가는 중");
  await page.waitForTimeout(6000); // the navigation map comes to the front with the new route

  step("drive to the academy and park");
  await page.click('#manual button[data-a="drive"]');
  await page.waitForTimeout(6000);
  await manual("park", 1000);
  await chat("도착했어요");

  step("민지 gets in: door open, seat, door close");
  await manual("door_open", 800);
  await manual("seat_on", 800);
  await manual("door_close", 500);
  await chat("뒷좌석 탑승 확인");

  step("엄마 records a cheer while they drive home");
  await page.click('#manual button[data-a="drive"]');
  await page.waitForTimeout(2000);
  await phone.locator("#who button[data-s='엄마']").click();
  await phone.locator("#cheerBtn").click();
  await phone.locator("#recBtn").click();
  await page.waitForTimeout(3500); // cheer_mom.wav is about 3 s
  await phone.locator("#recBtn").click();
  await phone.locator("#caption").fill("조심히 와~ 저녁 준비해 둘게");
  await phone.locator("#sendCheer").click();
  step("the recording plays in the car right away, while driving");
  await chat("차에서 재생됨");
  await page.waitForTimeout(5000);

  step("arrive home and park");
  carAppToFront();
  await manual("park", 0);
  await chat("집에 도착해서 주차했어요");
  await page.waitForTimeout(4000);
  await page.screenshot({ path: `${out}/family_demo_end.png` });

  const video = page.video();
  await context.close();
  audio.kill("SIGINT");
  await browser.close();
  const webm = await video.path();
  await new Promise(r => setTimeout(r, 1000));
  const mp4 = path.join(out, "family_demo.mp4");
  const offset = ((audioStart - videoStart) / 1000).toFixed(2);
  execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-i", webm, "-itsoffset", offset, "-i", audioFile,
    "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28",
    "-af", "loudnorm=I=-18:TP=-2", "-c:a", "aac", "-b:a", "128k", "-shortest", mp4]);
  console.log("video", mp4);
})().catch(e => { console.error(e); process.exit(1); });
