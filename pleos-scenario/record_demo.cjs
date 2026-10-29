// Usage: PW_CORE=<playwright-core dir> CHROME=<chromium binary> node record_demo.cjs <out dir> [scenario ids…]
// Record the scenario runner page, one video per scenario.
const { chromium } = require(process.env.PW_CORE);
const fs = require("fs");
const path = require("path");

const BASE = "http://127.0.0.1:8090";
const OUT = process.argv[2];
const ONLY = process.argv.slice(3);
const SIZE = { width: 1600, height: 900 };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function status() {
  return (await fetch(BASE + "/api/status")).json();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const scenarios = await (await fetch(BASE + "/api/scenarios")).json();
  const list = (Array.isArray(scenarios) ? scenarios : scenarios.scenarios).filter(s => !ONLY.length || ONLY.includes(s.id));
  const browser = await chromium.launch({ executablePath: process.env.CHROME });
  for (const s of list) {
    const ctx = await browser.newContext({ viewport: SIZE, recordVideo: { dir: OUT, size: SIZE } });
    const page = await ctx.newPage();
    await page.goto(BASE + "/");
    await page.waitForSelector(`button.run[data-id="${s.id}"]`);
    await page.waitForFunction(() => document.getElementById("screen").naturalWidth > 0, null, { timeout: 30000 });
    await sleep(2500);
    const t0 = Date.now();
    await page.click(`button.run[data-id="${s.id}"]`);
    let st;
    do {
      await sleep(500);
      st = await status();
    } while (st.runner.state === "running" && Date.now() - t0 < 240000);
    await sleep(5000); // let the last family message and screen settle
    const video = page.video();
    await ctx.close();
    const dest = path.join(OUT, `${s.id}.webm`);
    fs.renameSync(await video.path(), dest);
    console.log(`${s.id}\t${st.runner.state}\t${Math.round((Date.now() - t0) / 1000)}s\t${dest}`);
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
