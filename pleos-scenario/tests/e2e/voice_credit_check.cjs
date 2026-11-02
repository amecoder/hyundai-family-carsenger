// Usage: PW_CORE=<playwright-core dir> CHROME=<chromium binary> node voice_credit_check.cjs <base url>
// Prints when the voice-credit badge is on screen, in ms from the moment the recorded page is created.
// The runner page is answered 2 s late and the CPU slowed 6x: a badge added after the page loads would show up late.
const { chromium } = require(process.env.PW_CORE);
const { addVoiceCredit } = require("../../demo_audio.cjs");

const PAGE_DELAY_MS = 2000;

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME });
  try {
    const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
    await addVoiceCredit(ctx);
    const base = process.argv[2];
    await ctx.route(`${base}/`, route => setTimeout(() => route.continue(), PAGE_DELAY_MS));
    const t0 = Date.now();
    const page = await ctx.newPage();
    await (await ctx.newCDPSession(page)).send("Emulation.setCPUThrottlingRate", { rate: 6 });
    const seen = [];
    let inPhone = 0;
    const poll = (async () => {
      while (Date.now() - t0 < 7500) {
        // a sample taken while the page swaps documents throws; skip it rather than count it as "badge gone"
        const on = await page.evaluate(() => !!document.getElementById("voice-credit")).catch(() => null);
        if (on !== null) seen.push([Date.now() - t0, on]);
        const n = await page.frameLocator("iframe.phone").locator("#voice-credit").count().catch(() => 0);
        inPhone = Math.max(inPhone, n);
        await new Promise(r => setTimeout(r, 25));
      }
    })();
    await page.goto(base + "/");
    await poll;
    const shown = seen.find(([, on]) => on)?.[0] ?? null;
    const gone = shown === null ? null : seen.find(([t, on]) => t > shown && !on)?.[0] ?? null;
    console.log(JSON.stringify({ shown, gone, inPhone }));
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e.message || e); process.exit(1); });
