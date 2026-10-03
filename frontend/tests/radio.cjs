const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const calls = [];
  const station = {
    id: "d1234567-1234-1234-1234-123456789abc",
    name: "Fixture Jazz",
    country: "France",
    language: "French",
    codec: "MP3",
    bitrate: 192,
    tags: "jazz",
  };
  await page.route("**/api/v1/music/radio**", (route) => {
    const request = route.request();
    calls.push({ path: request.url(), method: request.method(), body: request.postDataJSON() });
    return route.fulfill({
      json:
        request.method() === "GET"
          ? request.url().includes("/facets")
            ? {
                genres: ["jazz", "rock", "lofi"],
                countries: [{ code: "FR", name: "France", stations: 3641 }],
                languages: ["french"],
              }
            : { items: request.url().includes("favorites") ? [] : [station] }
          : { status: "accepted" },
    });
  });
  await page.goto(base + "/music");
  const place = async (name) => {
    await page
      .getByRole("navigation", { name: "Listen" })
      .getByRole("button", { name, exact: true })
      .click();
    return page.getByRole("region", { name, exact: true });
  };
  // Radio is one of Listen's own places now (it was a sheet); genres are a list to pick from.
  const sheet = await place("Radio");
  await sheet.getByText("Fixture Jazz", { exact: true }).waitFor();
  await sheet.getByLabel("Radio genre").selectOption("jazz");
  await sheet.locator("label", { hasText: "Surprise me" }).click();
  await sheet.getByLabel("Radio country").selectOption("FR");
  await sheet.getByLabel("Plays on phones too").check();
  await sheet.getByText("Fixture Jazz", { exact: true }).waitFor();
  await sheet.getByRole("button", { name: /^(Add|Play) · Fixture Jazz$/ }).click();
  await page.getByText(/Station (queued|starting)/).waitFor();
  await sheet.getByRole("button", { name: "Favorite · Fixture Jazz", exact: true }).click();
  assert(
    calls.some(
      (x) =>
        x.path.includes("tag=jazz") &&
        x.path.includes("order=random") &&
        x.path.includes("country=FR") &&
        x.path.includes("https=true"),
    ),
    calls.map((x) => x.path).join("\n"),
  );
  assert(calls.some((x) => x.path.endsWith("/queue") && x.body.idempotency_key));
  assert(calls.some((x) => x.path.endsWith("/favorite")));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/radio-phone.png", fullPage: true });
  await browser.close();
  console.log(
    "Radio phone discovery/queue/favorite controls pass; network catalog and playback fixture-marked.",
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
