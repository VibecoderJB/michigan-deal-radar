// Browser smoke test: every route renders without JS errors or horizontal overflow at desktop
// and phone widths; filters, provenance popovers, CSV export and offline mode work.
//   BASE_URL=http://localhost:8000/ node smoke.mjs
import { readFileSync } from "node:fs";
import { chromium } from "playwright";

const BASE = process.env.BASE_URL || "http://localhost:8000/";
const ROUTES = ["dashboard", "deals", "map", "league", "precedents", "sectors", "sponsors", "active", "capital", "capital?tab=stakes",
  "briefing", "watchlist", "quality", "about", "analytics", "more"];
const failures = [];
const check = (ok, msg) => { console.log(`${ok ? "PASS" : "FAIL"} ${msg}`); if (!ok) failures.push(msg); };

const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});
for (const [name, viewport] of [["desktop", { width: 1400, height: 900 }], ["phone", { width: 390, height: 844 }]]) {
  const ctx = await browser.newContext({ viewport, acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  for (const r of ROUTES) {
    await page.goto(`${BASE}#/${r}`);
    await page.waitForSelector(".page-head, .tear-head", { timeout: 15000 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    const stamp = await page.locator("#asof").innerText();
    check(!overflow && /Data as of/.test(stamp), `${name} #/${r} renders with data-as-of stamp and no overflow`);
  }
  await page.goto(`${BASE}#/deals`);
  await page.waitForSelector("#result-bar strong");
  const before = Number(await page.locator("#result-bar strong").first().innerText());
  await page.selectOption('[data-f="category"]', "M&A");
  await page.waitForTimeout(200);
  const after = Number(await page.locator("#result-bar strong").first().innerText());
  check(after > 0 && after <= before, `${name} category filter (${before} -> ${after})`);
  if (name === "desktop") {
    const dl = page.waitForEvent("download");
    await page.click("#export-csv");
    const lines = readFileSync(await (await dl).path(), "utf8").trim().split("\r\n");
    check(lines.length - 1 === after, `CSV export rows ${lines.length - 1} == ${after}`);
    await page.locator("#rows tr.clickable").first().click();
  } else {
    await page.locator("#cards .deal-item").first().click();
  }
  await page.waitForSelector(".tear-head");
  await page.locator(".fn").first().click();
  check((await page.locator(".prov.open").count()) === 1, `${name} provenance popover opens`);
  if (name === "desktop") {
    await page.goto(`${BASE}#/dashboard`);
    await page.waitForSelector(".kpi");
    const swReady = await page.evaluate(async () => Boolean((await navigator.serviceWorker.ready).active));
    check(swReady, "service worker active");
    await page.reload();
    await page.waitForSelector(".kpi");
    await ctx.setOffline(true);
    await page.reload();
    await page.waitForSelector(".kpi", { timeout: 10000 }).catch(() => {});
    check((await page.locator(".kpi").count()) > 0, "dashboard loads offline");
    await ctx.setOffline(false);
  }
  check(errors.length === 0, `${name} no console errors ${JSON.stringify(errors.slice(0, 3))}`);
  await ctx.close();
}
await browser.close();
if (failures.length) {
  console.error(`${failures.length} check(s) failed`);
  process.exit(1);
}
