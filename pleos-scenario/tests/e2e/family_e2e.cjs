// Drives the family web app in Chromium with a fake microphone: text, pickup request, recorded cheer.
// Usage: PW_CORE=<playwright-core dir> CHROME=<chromium binary> node family_e2e.cjs <base url> <screenshot dir>
const { chromium } = require(process.env.PW_CORE);

(async () => {
  const [base, shots] = process.argv.slice(2);
  const browser = await chromium.launch({
    executablePath: process.env.CHROME,
    args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
  });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.context().grantPermissions(["microphone"], { origin: base });
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  await page.goto(`${base}/family?as=민지`);
  await page.waitForSelector("#link:has-text('연결됨')");

  await page.fill("#text", "오늘 학원 늦게 끝나");
  await page.press("#text", "Enter");
  await page.waitForSelector(".msg.me:has-text('오늘 학원 늦게 끝나')");

  await page.click("#pickBtn");
  await page.click("#places button:has-text('○○수학학원 앞')");
  await page.waitForSelector(".msg.me:has-text('데리러 와 · ○○수학학원 앞')");

  await page.click("#cheerBtn");
  await page.click("#recBtn");
  await page.waitForTimeout(2200);
  await page.click("#recBtn");
  await page.waitForSelector("#preview:not([hidden])");
  await page.fill("#caption", "조심히 와");
  await page.screenshot({ path: `${shots}/family_preview.png` });
  await page.click("#sendCheer");
  await page.waitForSelector(".msg.me:has-text('응원 음성 (0:02)')");
  await page.screenshot({ path: `${shots}/family_sent.png` });

  console.log(JSON.stringify({ errors }));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
