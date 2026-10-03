// The TV remote's volume is a slider: dragging sends nothing, letting go sends one exact level,
// then the remote shows what the TV reports. Steps stay only where a soundbar plays the sound.
// The TVs are mocked; nothing reaches a real TV.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const shots = process.env.HOUSEOS_SHOTS || "";
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  let volume = 30;
  const sent = [];
  const tv = (id, name, target, caps, extra = {}) => ({
    id,
    name,
    target,
    adapter: target === "tv" ? "home_assistant" : "cast",
    inputs: [],
    capabilities: {
      dpad: false,
      volume: true,
      mute: true,
      playback: false,
      power: true,
      input: false,
      remote_pairable: false,
      paired: false,
      ...caps,
    },
    state: { reachable: true, on: true, volume, muted: false, ...extra },
  });
  await page.route("**/api/v1/tv", (route) =>
    route.fulfill({
      json: {
        items: [
          tv("salon", "Salon TV", "tv", { volume_level: true }),
          tv("lg", "OLED TV", "tv", { volume_level: false }),
        ],
      },
    }),
  );
  await page.route("**/api/v1/tv/*/remote", (route) => {
    const body = route.request().postDataJSON();
    sent.push(body.key + ":" + (body.level ?? ""));
    if (body.key === "VOLUME_SET") volume = body.level;
    route.fulfill({ json: { status: "sent" } });
  });
  await page.route("**/api/v1/house-settings", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), home_assistant: false } });
  });
  await page.goto(base + "/smart-home");
  // The remote is inline on the page: no tap to reach it.
  const salon = page.locator(".tv-remote", { hasText: "Salon TV" });
  await salon.waitFor();
  const slider = salon.locator(".tv-remote__volume input");
  assert.equal(
    await salon.getByRole("button", { name: /Volume up/i }).count(),
    0,
    "a slider, not steps",
  );
  await slider.focus();
  for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(400);
  assert.deepEqual(
    sent,
    ["VOLUME_SET:31", "VOLUME_SET:32", "VOLUME_SET:33"],
    "each release sends one exact level",
  );
  await page.waitForTimeout(300);
  assert.equal(
    await salon.locator(".tv-remote__volume b").innerText(),
    "33",
    "shows what the TV now reports",
  );
  // Several TVs: a small switcher chooses which one the remote controls.
  await page.locator(".tv-remotes .ds-segmented label", { hasText: "OLED TV" }).click();
  const lg = page.locator(".tv-remote", { hasText: "OLED TV" });
  await lg.waitFor();
  assert.equal(await lg.locator(".tv-remote__rocker").count(), 1, "soundbar: volume steps");
  assert.equal(await lg.locator(".tv-remote__volume").count(), 0, "soundbar: steps only");
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  if (shots) await salon.screenshot({ path: `${shots}/tv-remote-volume.png` });
  await browser.close();
  console.log("tv-remote-volume: PASS");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
