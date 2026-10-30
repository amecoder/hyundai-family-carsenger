// Usage: PW_CORE=<playwright-core dir> CHROME=<chromium binary> [ADB=<adb>] node record_demo.cjs <out dir> [scenario ids…]
// Record the scenario runner page, one mp4 per scenario, with the emulator's sound and on-screen step captions.
// Captions are drawn as an overlay inside the page (so they are part of the recording); sound is the PC's default
// audio output monitor recorded with parecord and muxed with ffmpeg. Needs ./start_demo.sh running.
const { chromium } = require(process.env.PW_CORE);
const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const BASE = "http://127.0.0.1:8090";
const OUT = process.argv[2];
const ONLY = process.argv.slice(3);
const SIZE = { width: 1600, height: 900 };
const ADB = process.env.ADB || `${process.env.HOME}/Android/Sdk/platform-tools/adb`;
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function status() {
  return (await fetch(BASE + "/api/status")).json();
}

// the car app runs as a foreground service, but its screen (cards, cheer player) is only visible in front
function carAppToFront() {
  try {
    execFileSync(ADB, ["shell", "am", "start", "--user", "10", "-n", "dev.gajokseok.car/.MainActivity"], { stdio: "ignore" });
  } catch (e) {
    console.error("car app to front failed:", e.message);
  }
}

function startAudioCapture(file) {
  const sink = execFileSync("pactl", ["get-default-sink"], { encoding: "utf8" }).trim();
  return spawn("parecord", ["-d", `${sink}.monitor`, "--file-format=wav", file], { stdio: "ignore" });
}

// draws (or clears, when lines is empty) the caption box at the bottom of the runner page
async function caption(page, lines) {
  await page.evaluate(ls => {
    let box = document.getElementById("rec-caption");
    if (!box) {
      box = document.createElement("div");
      box.id = "rec-caption";
      box.style.cssText = "position:fixed;left:50%;bottom:28px;transform:translateX(-50%);width:min(1240px,92vw);z-index:99999;"
        + "background:rgba(17,24,39,.92);color:#fff;border-radius:14px;padding:16px 24px;font:500 22px/1.45 'Noto Sans CJK KR',sans-serif;"
        + "box-shadow:0 8px 24px rgba(0,0,0,.35)";
      document.body.appendChild(box);
    }
    box.style.display = ls.length ? "block" : "none";
    box.innerHTML = ls.map(([cls, text]) => {
      const style = { head: "font-size:26px;font-weight:700;color:#fbbf24", body: "color:#e5e7eb", check: "color:#86efac;font-weight:600" }[cls];
      const el = document.createElement("div");
      el.textContent = text;
      return `<div style="${style}">${el.innerHTML}</div>`;
    }).join("");
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

async function recordOne(browser, s) {
  const ctx = await browser.newContext({ viewport: SIZE, recordVideo: { dir: OUT, size: SIZE } });
  const page = await ctx.newPage();
  const videoStart = Date.now();
  const audioFile = path.join(OUT, `${s.id}.wav`);
  const audio = startAudioCapture(audioFile);
  const audioStart = Date.now();

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
  let shown = -1;
  let st;
  do {
    await sleep(300);
    st = await status();
    const i = st.runner.step_index;
    if (st.runner.scenario === s.id && i !== shown && i < s.steps.length) {
      shown = i;
      await caption(page, stepLines(s, i));
    }
  } while (st.runner.state === "running" && Date.now() - t0 < 240000);
  await sleep(4000); // let the last family message, voice and screen settle under the last caption
  await caption(page, [["head", `끝 · ${s.title}`], ["check", st.runner.state === "done" ? "모든 단계를 실행했습니다" : `실행 상태: ${st.runner.state}`]]);
  await sleep(3500); // the screencast drops the last second, so hold the end caption a little longer

  const video = page.video();
  const wallSeconds = (Date.now() - videoStart) / 1000;
  await ctx.close();
  audio.kill("SIGINT");
  const webm = await video.path();
  await sleep(1000);
  const mp4 = path.join(OUT, `${s.id}.mp4`);
  const offset = ((audioStart - videoStart) / 1000).toFixed(2);
  execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-i", webm, "-itsoffset", offset, "-i", audioFile,
    "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28",
    "-af", "loudnorm=I=-18:TP=-2", "-c:a", "aac", "-b:a", "128k", "-shortest", mp4]);
  fs.unlinkSync(webm);
  fs.unlinkSync(audioFile);
  return { state: st.runner.state, wallSeconds, steps: shown + 1, mp4 };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const scenarios = await (await fetch(BASE + "/api/scenarios")).json();
  const list = (Array.isArray(scenarios) ? scenarios : scenarios.scenarios).filter(s => !ONLY.length || ONLY.includes(s.id));
  const browser = await chromium.launch({ executablePath: process.env.CHROME });
  for (const s of list) {
    const r = await recordOne(browser, s);
    console.log(`${s.id}\t${r.state}\tsteps ${r.steps}/${s.steps.length}\twall ${r.wallSeconds.toFixed(1)}s\t${r.mp4}`);
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
