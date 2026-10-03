// A TV from Home Assistant (an LG webOS whose sound goes to a soundbar) gets every control it
// reports: power, playback, volume steps instead of the slider, its sources and a remote.
// Home Assistant is mocked; nothing reaches a real TV.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const shots = process.env.HOUSEOS_SHOTS || "";
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  const tv = {
    id: "media_player.oled_tv",
    name: "OLED TV",
    domain: "media_player",
    area: "Salon",
    state: "playing",
    attributes: {
      volume_pct: 71,
      source: "Netflix",
      app_name: "Netflix",
      source_list: ["HDMI 1", "Netflix", "YouTube", "Live TV"],
      external_speakers: true,
      is_volume_muted: false,
    },
    actions: [
      "turn_off",
      "play",
      "pause",
      "stop",
      "previous",
      "next",
      "volume",
      "volume_up",
      "volume_down",
      "mute",
      "unmute",
      "source",
      "key",
    ],
  };
  for (const [width, height] of [
    [390, 844],
    [1440, 900],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } });
    await require("./session.cjs")(context, base);
    const page = await context.newPage();
    const sent = [];
    await page.route("**/api/v1/house-settings", async (route) => {
      const response = await route.fetch();
      await route.fulfill({ response, json: { ...(await response.json()), home_assistant: true } });
    });
    await page.route("**/api/v1/home", (route) =>
      route.fulfill({
        json: { curated: true, favorites: [], areas: [{ name: "Salon", entities: [tv] }] },
      }),
    );
    // No TV remote on the page: the card has its own arrows.
    await page.route("**/api/v1/tv", (route) => route.fulfill({ json: { items: [] } }));
    await page.route("**/api/v1/home/*/action", (route) => {
      const body = route.request().postDataJSON();
      sent.push(body);
      route.fulfill({ json: { status: "command_sent", entity: tv } });
    });
    await page.goto(base + "/smart-home");
    const card = page.locator(".smart-device[data-domain='media_player']");
    await card.waitFor();
    assert.match(await card.locator(".smart-device__title small").innerText(), /Netflix/);
    assert.equal(
      await card.locator("input[type=range]").count(),
      0,
      "soundbar: steps, not the slider",
    );
    await card.getByRole("button", { name: "Volume up" }).click();
    await card.getByRole("button", { name: "Pause" }).click();
    await card.locator("select").selectOption("YouTube");
    await card.getByRole("button", { name: "Remote: arrows and OK" }).click();
    await card.getByRole("button", { name: "OK", exact: true }).click();
    await card.getByRole("button", { name: "Back" }).click();
    await page.waitForTimeout(300);
    assert.deepEqual(
      sent.map((s) => s.action + ":" + (s.value ?? "")),
      ["volume_up:", "pause:", "source:YouTube", "key:DPAD_CENTER", "key:BACK"],
    );
    const box = await card.boundingBox();
    assert.ok(box.x >= 0 && box.x + box.width <= width, "the card fits the screen");
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    if (shots) await card.screenshot({ path: `${shots}/smart-home-tv-${width}.png` });
    // The pad sits inside the card: the name keeps its width (no squeezed extra column).
    const name = await card.locator(".smart-device__title strong").boundingBox();
    assert.ok(name.height < 40, "the TV's name stays on one line with the pad open");
    await context.close();
  }
  // With the TV in the page's remote, the card's Remote button brings that remote up (one
  // remote on the page, not two): chosen, in view and focused for the arrows. Nothing is sent.
  for (const [width, height] of [
    [390, 844],
    [1440, 900],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } });
    await require("./session.cjs")(context, base);
    const page = await context.newPage();
    const writes = [];
    await page.route("**/api/**", (route) => {
      if (route.request().method() === "GET") return route.fallback();
      writes.push(route.request().url());
      route.fulfill({ json: {} });
    });
    await page.route("**/api/v1/house-settings", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      const response = await route.fetch();
      await route.fulfill({ response, json: { ...(await response.json()), home_assistant: true } });
    });
    await page.route("**/api/v1/home", (route) =>
      route.fulfill({
        json: { curated: true, favorites: [], areas: [{ name: "Salon", entities: [tv] }] },
      }),
    );
    const remote = (id, name, target, dpad) => ({
      id,
      name,
      target,
      adapter: target === "tv" ? "home_assistant" : "cast",
      inputs: [],
      capabilities: { dpad, volume: true, volume_level: true, mute: true, power: true },
      state: { reachable: true, on: true, volume: 20 },
    });
    await page.route("**/api/v1/tv", (route) =>
      route.fulfill({
        json: {
          items: [remote("k", "Kitchen TV", "tv", true), remote("s", "OLED TV", "tv", true)],
        },
      }),
    );
    await page.goto(base + "/smart-home");
    const card = page.locator(".smart-device[data-domain='media_player']");
    await card.waitFor();
    await page.locator(".tv-remote", { hasText: "Kitchen TV" }).waitFor();
    await card.getByRole("button", { name: "Remote: arrows and OK" }).click();
    assert.equal(await card.locator(".tv-remote__pad").count(), 0, "no second pad in the card");
    const panel = page.locator(".tv-remote", { hasText: "OLED TV" });
    await panel.waitFor();
    await page.waitForFunction(() => document.activeElement?.classList.contains("tv-remote"));
    const box = await panel.boundingBox();
    assert.ok(box.y < height && box.y + box.height > 0, "the remote is in view");
    assert.deepEqual(writes, [], "choosing the remote sends nothing");
    await context.close();
  }
  await browser.close();
  console.log("smart-home-tv: PASS");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
