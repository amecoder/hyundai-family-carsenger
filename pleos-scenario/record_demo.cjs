// Usage: PW_CORE=<playwright-core dir> CHROME=<chromium binary> [ADB=<adb>] node record_demo.cjs <out dir> [scenario ids…]
// Record the scenario runner page, one mp4 per scenario, with the emulator's sound and on-screen step captions.
// Captions are drawn as an overlay inside the page (so they are part of the recording); the sound track is rebuilt from
// the runner's sound log (demo_audio.cjs) and muxed with ffmpeg. Needs ./start_demo.sh running, uv and ffmpeg.
const { chromium } = require(process.env.PW_CORE);
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const { collectSounds, muxWithSounds, addVoiceCredit, driverOptsInForDemo } = require("./demo_audio.cjs");

const BASE = "http://127.0.0.1:8090";
const OUT = process.argv[2];
const ONLY = process.argv.slice(3);
const SIZE = { width: 1600, height: 900 };
const ADB = process.env.ADB || `${process.env.HOME}/Android/Sdk/platform-tools/adb`;
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function status() {
  return (await fetch(BASE + "/api/status")).json();
}

// clear the previous scenario's family chat and car cards before the video starts, so the title caption is not shown
// over the last scenario's screen (the scenario's own first step resets again with its own trip)
async function resetBeforeRecording() {
  // the POST returns before the runner picks the job up, so a reset left "done" from before is not this one finishing
  const stale = (await status()).runner.scenario === "manual_reset";
  const r = await fetch(BASE + "/api/manual/reset", { method: "POST" });
  if (!r.ok) throw new Error(`녹화 전 초기화를 시작하지 못했습니다 (HTTP ${r.status})`);
  const until = Date.now() + 20000;
  let seenRunning = false;
  while (Date.now() < until) {
    const { runner } = await status();
    if (runner.scenario === "manual_reset" && runner.state === "running") seenRunning = true;
    if (runner.scenario === "manual_reset" && runner.state === "done" && (seenRunning || !stale)) return;
    await sleep(200);
  }
  throw new Error("녹화 전 초기화가 20초 안에 끝나지 않았습니다");
}

// the car app runs as a foreground service, but its screen (cards, cheer player) is only visible in front
function carAppToFront() {
  try {
    execFileSync(ADB, ["shell", "am", "start", "--user", "10", "-n", "dev.gajokseok.car/.MainActivity"], { stdio: "ignore" });
  } catch (e) {
    console.error("car app to front failed:", e.message);
  }
}

// draws the caption box at the bottom of the runner page
async function caption(page, lines) {
  await page.evaluate(ls => {
    const styles = { head: "font-size:26px;font-weight:700;color:#fbbf24", body: "color:#e5e7eb", check: "color:#86efac;font-weight:600" };
    let box = document.getElementById("rec-caption");
    if (!box) {
      box = document.createElement("div");
      box.id = "rec-caption";
      box.style.cssText = "position:fixed;left:50%;bottom:28px;transform:translateX(-50%);width:min(1240px,92vw);z-index:99999;"
        + "background:rgba(17,24,39,.92);color:#fff;border-radius:14px;padding:16px 24px;font:500 22px/1.45 'Noto Sans CJK KR',sans-serif;"
        + "box-shadow:0 8px 24px rgba(0,0,0,.35)";
      document.body.appendChild(box);
    }
    box.replaceChildren(...ls.map(([cls, text]) => {
      const el = document.createElement("div");
      el.style.cssText = styles[cls];
      el.textContent = text;
      return el;
    }));
  }, lines);
}

const stepLines = (s, i) => {
  const step = s.steps[i];
  return [
    ["head", `${i + 1}/${s.steps.length} · ${step.title}`],
    ["body", `상황: ${step.narration}`],
    ...(step.expect ? [["check", `확인할 것: ${step.expect}`]] : []),
  ];
};

// the runner keeps the previous scenario's "done" until it picks up the click, so wait for this one to start
async function waitForStart(id) {
  const until = Date.now() + 15000;
  while (Date.now() < until) {
    const st = await status();
    if (st.runner.scenario === id && st.runner.state === "running") return;
    await sleep(200);
  }
  throw new Error(`${id}: 실행기가 15초 안에 시나리오를 시작하지 않았습니다`);
}

async function recordOne(browser, s) {
  await resetBeforeRecording();
  const ctx = await browser.newContext({ viewport: SIZE, recordVideo: { dir: OUT, size: SIZE } });
  let webm = null;
  try {
    await addVoiceCredit(ctx);
    const videoStart = Date.now(); // the page's video starts when the page is created
    const page = await ctx.newPage();

    await page.goto(BASE + "/");
    await page.waitForSelector(`button.run[data-id="${s.id}"]`);
    await page.waitForFunction(() => document.getElementById("screen").naturalWidth > 0, null, { timeout: 30000 });
    carAppToFront();
    await caption(page, [["head", `시나리오: ${s.title}`], ["body", s.summary]]);
    await sleep(4000);

    const t0 = Date.now();
    await page.click(`button.run[data-id="${s.id}"]`);
    // buttons near the bottom of the list scroll the page; keep the emulator and phone in view
    await page.evaluate(() => window.scrollTo(0, 0));
    await waitForStart(s.id);
    let shown = -1;
    let st;
    do {
      st = await status();
      const i = st.runner.step_index;
      if (i !== shown && i < s.steps.length) {
        shown = i;
        await caption(page, stepLines(s, i));
      }
      if (st.runner.state === "running") await sleep(300);
    } while (st.runner.state === "running" && Date.now() - t0 < 240000);
    const complete = st.runner.state === "done" && shown + 1 === s.steps.length;
    await sleep(4000); // let the last family message, voice and screen settle under the last caption
    await caption(page, [["head", `끝 · ${s.title}`], ["check", complete ? "모든 단계를 실행했습니다" : `실행 상태: ${st.runner.state}`]]);
    await sleep(3500); // the screencast drops the last second, so hold the end caption a little longer

    const video = page.video();
    const wallSeconds = (Date.now() - videoStart) / 1000;
    await ctx.close();
    webm = await video.path();
    if (!complete) throw new Error(`${s.id}: 상태 ${st.runner.state}, 단계 ${shown + 1}/${s.steps.length} — 녹화본을 쓰지 않습니다 (${webm})`);

    const mp4 = path.join(OUT, `${s.id}.mp4`);
    const sounds = await collectSounds(BASE, videoStart, OUT);
    muxWithSounds(webm, sounds, mp4);
    fs.rmSync(webm, { force: true });
    sounds.filter(p => p.kind === "clip").forEach(p => fs.rmSync(p.file, { force: true }));
    return { wallSeconds, steps: shown + 1, sounds: sounds.length, mp4 };
  } finally {
    await ctx.close().catch(() => {});
  }
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const scenarios = await (await fetch(BASE + "/api/scenarios")).json();
  const list = (Array.isArray(scenarios) ? scenarios : scenarios.scenarios).filter(s => !ONLY.length || ONLY.includes(s.id));
  carAppToFront(); // a car app frozen in the background would miss the settings command
  await driverOptsInForDemo(BASE);
  const browser = await chromium.launch({ executablePath: process.env.CHROME });
  try {
    for (const s of list) {
      const r = await recordOne(browser, s);
      console.log(`${s.id}\tdone\tsteps ${r.steps}/${s.steps.length}\twall ${r.wallSeconds.toFixed(1)}s\tsounds ${r.sounds}\t${r.mp4}`);
    }
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e.message || e); process.exit(1); });
