// Turns usage recording on in the family web app, makes one two-way exchange, then reads the retention dashboard.
// Usage: PW_CORE=<playwright-core dir> CHROME=<chromium binary> node analytics_e2e.cjs <base url> <screenshot dir>
const { chromium } = require(process.env.PW_CORE);

(async () => {
  const [base, shots] = process.argv.slice(2);
  const browser = await chromium.launch({ executablePath: process.env.CHROME });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  page.on("dialog", d => { errors.push(`dialog: ${d.message()}`); d.dismiss(); });

  await page.goto(`${base}/family?as=엄마`);
  await page.waitForSelector("#consentBar:not([hidden])");
  if (await page.isChecked("#consentBox")) errors.push("consent was on before the family agreed");
  await page.check("#consentBox");
  await page.waitForFunction(() => !document.getElementById("consentBox").disabled);
  await page.screenshot({ path: `${shots}/family_consent.png` });

  await page.fill("#text", "조심히 와");
  await page.press("#text", "Enter");
  await page.waitForSelector(".msg.me:has-text('조심히 와')");
  // 엄마 sends a voice cheer (the same request the record sheet makes) and the car plays it: one two-way exchange.
  // The server counts a played cheer only when it matches a cheer the family really sent.
  await page.evaluate(async b => {
    const sent = await fetch(`${b}/api/family/cheer?sender=엄마&text=${encodeURIComponent("잘 다녀와")}&duration_ms=1000`,
      { method: "POST", headers: { "Content-Type": "audio/webm" }, body: new Uint8Array([1, 2, 3]) });
    if (!sent.ok) throw new Error(`cheer not sent: ${sent.status}`);
    await fetch(`${b}/api/car/event`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "cheer_played", text: "엄마: 잘 다녀와", event: "cheer_played" }) });
  }, base);

  const dash = await browser.newPage({ viewport: { width: 900, height: 900 } });
  dash.on("pageerror", e => errors.push(String(e)));
  await dash.goto(`${base}/analytics`);
  await dash.waitForSelector("#cohorts table");
  const kpis = await dash.textContent("#kpis");
  if (!kpis.includes("동의함")) errors.push(`kpis without consent: ${kpis}`);
  const firstWeek = await dash.textContent("#cohorts tbody tr td:nth-child(3)");
  if (!firstWeek.startsWith("100%")) errors.push(`week 0 should be 100%: ${firstWeek}`);
  await dash.screenshot({ path: `${shots}/analytics_dashboard.png`, fullPage: true });

  // turning consent off wipes this family's events
  await page.uncheck("#consentBox");
  await page.waitForFunction(() => !document.getElementById("consentBox").disabled);
  await dash.reload();
  await dash.waitForSelector("#cohorts:has-text('아직 핵심 이벤트가 없습니다')");

  await browser.close();
  console.log(JSON.stringify({ errors }));
})().catch(e => { console.error(e); process.exit(1); });
