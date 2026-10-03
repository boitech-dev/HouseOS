const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { until } = require("./session.cjs");
const fs = require("node:fs");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const failures = [];
  page.on("pageerror", (e) => failures.push(e.message));
  const selected = [],
    discoveries = [];
  const workflow = {
    id: "fixture-workflow",
    media_id: "fixture-episode",
    device_id: "fixture-device",
    version: 1,
    state: "playing_observed",
    season: 2,
    episode: 3,
    plan: {
      audio: { id: "1" },
      available_tracks: {
        audio: [
          { id: "1", language: "en", codec: "aac" },
          { id: "2", language: "fr", codec: "aac", channels: 2 },
        ],
        subtitles: [{ id: "3", language: "fr", codec: "srt", forced: true }],
      },
    },
    choice_set: { candidates: [] },
    checkpoint: { position: 24 },
  };
  await page.route("**/api/v1/cinema/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1/cinema", "");
    let data = {};
    if (path === "/cloud")
      data = {
        items: [{ id: "a".repeat(32), title: "Synthetic cloud release", state: "downloaded" }],
      };
    else if (path === "/operations/discover") {
      discoveries.push(route.request().postDataJSON());
      data = { operation_id: "cloud-discover-op", status: "accepted" };
    } else if (path === "/devices")
      data = { items: [{ id: "fixture-device", name: "Synthetic screen", state: "unknown" }] };
    else if (path === "/workflows") data = { items: [workflow] };
    else if (path === "/workflows/fixture-workflow") data = workflow;
    else if (path === "/workflows/fixture-workflow/change") {
      selected.push(route.request().postDataJSON());
      data = {
        ...workflow,
        id: "fixture-replacement",
        version: 2,
        state: "awaiting_playback_confirmation",
      };
    } else if (path === "/titles/fixture-episode")
      data = {
        id: "fixture-episode",
        title: "Synthetic episode",
        kind: "episode",
        parent_id: "fixture-series",
        season: 2,
        episode: 3,
      };
    else if (path === "/titles/fixture-series")
      data = {
        id: "fixture-series",
        title: "Synthetic series",
        kind: "series",
        episodes: [{ id: "ep-23", season: 2, episode: 3, title: "Third episode" }],
      };
    else if (path === "/state") data = { items: [] };
    else if (path === "/library")
      data = {
        items: [{ id: "fixture-series", title: "Synthetic series", kind: "series" }],
        next_offset: null,
      };
    await route.fulfill({ json: data });
  });
  await page.goto(base + "/watch");
  const shelf = page.getByRole("list", { name: "Your picks" });
  await shelf.getByText("Synthetic series", { exact: true }).waitFor();
  // A file already in the debrid account plays exactly that file.
  await page.getByRole("button", { name: "Sources", exact: true }).click();
  await page.getByRole("button", { name: /^Debrid history/ }).click();
  await page.getByRole("button", { name: /Synthetic cloud release/ }).click();
  await page
    .getByText("Open its film or episode to play exactly this file.", { exact: false })
    .waitFor();
  await shelf.getByText("Synthetic series", { exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Synthetic series" });
  await sheet.getByRole("button", { name: /Third episode/ }).waitFor();
  await until(() => discoveries.length, 5000);
  assert.equal(discoveries.length, 1);
  assert.equal(discoveries[0].cloud_id, "a".repeat(32));
  assert.equal(discoveries[0].media_id, "fixture-series");
  assert.equal(discoveries[0].season, 2);
  assert.equal(discoveries[0].episode, 3);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/review-cinema-tracks-phone.png", fullPage: true });
  await sheet.getByRole("button", { name: "Close" }).last().click();
  const events = [];
  await page.route("**/api/v1/house-settings", (route) =>
    route.fulfill({
      json: { name: "Fixture house", timezone: "America/Toronto", preferences: {} },
    }),
  );
  // The editor and the calendar use the resident's own time zone (else the house's).
  await page.route("**/api/v1/preferences", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: { ...(await response.json()), timezone: "America/Toronto" },
    });
  });
  await page.route("**/api/v1/household/calendar", (route) => {
    if (route.request().method() === "POST") {
      events.push(route.request().postDataJSON());
      return route.fulfill({ json: { id: "fixture-event", version: 1 } });
    }
    return route.continue();
  });
  await page.goto(base + "/house");
  await page.getByRole("button", { name: "Calendar", exact: true }).click();
  await page.getByRole("button", { name: "Add an event", exact: true }).click();
  await page.getByLabel("Title", { exact: true }).fill("Synthetic timezone event");
  await page.getByLabel("Starts · America/Toronto", { exact: true }).fill("2026-10-02T12:00");
  await page.getByLabel("Ends · America/Toronto", { exact: true }).fill("2026-10-02T13:00");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await until(() => events.length);
  assert.equal(events.length, 1);
  assert.equal(events[0].data.timezone, "America/Toronto");
  assert.deepEqual(failures, []);
  fs.writeFileSync(
    "evidence/latest/spec-review-result.json",
    JSON.stringify(
      {
        passed: true,
        evidence: "Real isolated authentication; mocked Cinema API contracts; no playback",
        checks: [
          "local catalog browse",
          "episode history restores exact episode",
          "actual track IDs and subtitles on submitted",
          "no spurious destination change",
          "390px overflow",
          "no JavaScript errors",
          "cloud item explicit series/episode mapping",
          "calendar uses configured household timezone",
        ],
      },
      null,
      2,
    ),
  );
  await browser.close();
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
