const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
// The film's volume is the TV's own when Home Assistant reaches it: the number the TV shows,
// not the Chromecast's separate level. All mocked: nothing plays.
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const sent = [];
  await page.route(
    "**/api/v1/cinema/current",
    (r) =>
      r.fulfill({
        json: {
          current: {
            id: "film",
            title: "Fixture film",
            version: 3,
            state: "playing_observed",
            checkpoint: { position: 60 },
            duration: 3600,
            device_id: "screen-1",
            volume_supported: true,
            volume: 91,
          },
        },
      }), // fmt: skip
  );
  let tvVolume = 22;
  await page.route(
    "**/api/v1/tv",
    (r) =>
      r.fulfill({
        json: {
          items: [
            {
              id: "screen-1",
              target: "tv",
              name: "Living-room TV",
              capabilities: { volume: true, volume_level: true },
              state: { volume: tvVolume },
            },
            {
              id: "screen-1",
              target: "device",
              name: "Chromecast",
              capabilities: { volume_level: true },
              state: { volume: 91 },
            },
          ],
        },
      }), // fmt: skip
  );
  await page.route("**/api/v1/tv/screen-1/remote", (r) => {
    const body = r.request().postDataJSON();
    sent.push(body);
    tvVolume = body.level;
    return r.fulfill({ json: { status: "sent" } });
  });
  await page.goto(base + "/house");
  await page.locator(".shell__now").getByText("Fixture film", { exact: false }).waitFor();
  await page.locator(".shell__now .shell__now-open").click();
  const sheet = page.getByRole("dialog", { name: "Now playing" });
  const slider = sheet.getByLabel("TV volume");
  await slider.waitFor();
  assert.equal(await slider.inputValue(), "22", "the TV's own number, not the Chromecast's 91");
  assert.equal(await sheet.getByLabel("Movie volume").count(), 0);
  await slider.focus();
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(
    () => document.querySelector('input[aria-label="TV volume"]')?.value === "23",
  );
  for (let i = 0; i < 20 && !sent.length; i++) await page.waitForTimeout(100);
  assert.deepEqual(sent[0], { key: "VOLUME_SET", level: 23, target: "tv" });
  await browser.close();
  console.log("PASS film controls set the TV's own volume, showing the TV's number");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
