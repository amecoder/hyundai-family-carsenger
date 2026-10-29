// Records the hands-on family app demo against the real emulator: family app (iframe) + manual controls + taps on the car screen.
// Usage: PW_CORE=<playwright-core dir> CHROME=<chromium binary> [ADB=<adb>] node record_family_demo.cjs <out dir>
// Needs ./start_demo.sh running. Chrome's fake microphone records a test tone, not a voice.
const { execFileSync } = require("child_process");
const fs = require("fs");
const { chromium } = require(process.env.PW_CORE);

const BASE = "http://127.0.0.1:8090";
const ADB = process.env.ADB || `${process.env.HOME}/Android/Sdk/platform-tools/adb`;
const adb = (...args) => execFileSync(ADB, args, { encoding: "utf8" });

// the car app is frozen by Android while it is in the background, so keep it in front
const carAppToFront = () => adb("shell", "am", "start", "--user", "10", "-n", "dev.gajokseok.car/.MainActivity");

function tapCarButton(label) {
  adb("shell", "uiautomator", "dump", "/sdcard/ui.xml");
  const xml = adb("shell", "cat", "/sdcard/ui.xml");
  const m = xml.match(new RegExp(`text="${label}"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`));
  if (!m) throw new Error(`car screen has no "${label}" button`);
  const [x1, y1, x2, y2] = m.slice(1).map(Number);
  adb("shell", "input", "tap", String((x1 + x2) >> 1), String((y1 + y2) >> 1));
}

(async () => {
  const out = process.argv[2];
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    executablePath: process.env.CHROME,
    args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
  });
  const context = await browser.newContext({ viewport: { width: 1600, height: 900 }, recordVideo: { dir: out, size: { width: 1600, height: 900 } } });
  await context.grantPermissions(["microphone"], { origin: BASE });
  const page = await context.newPage();
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
  step("driver taps 추가 on the car screen");
  tapCarButton("추가");
  await chat("가는 중");

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
  await page.waitForTimeout(3000);
  await phone.locator("#recBtn").click();
  await phone.locator("#caption").fill("조심히 와~ 저녁 준비해 둘게");
  await phone.locator("#sendCheer").click();
  await page.waitForTimeout(5000);

  step("arrive home and park: the recording plays");
  await manual("park", 0);
  await chat("차에서 재생됨");
  await page.waitForTimeout(5000);
  await page.screenshot({ path: `${out}/family_demo_end.png` });

  const video = page.video();
  await context.close();
  console.log("video", await video.path());
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
