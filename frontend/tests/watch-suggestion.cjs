// Watch: shelves, a title's "Tonight" card checks versions, nothing plays until the tap,
// tracks and start time are changeable, and the tap sends exactly what the card shows.
// Real isolated login; every Cinema read/write is intercepted, so no TV is touched.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { until } = require("./session.cjs");
const fs = require("node:fs");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    errors = [],
    writes = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const poster = fs.readFileSync(__dirname + "/../public/art/tv-bezel.png");
  const film = {
    id: "film",
    title: "Fixture Night",
    kind: "movie",
    year: 2021,
    genres: ["Drama"],
    description: "A synthetic film used only by browser tests.",
    poster: "/api/v1/cinema/titles/film/poster",
    progress: { position: 4416, duration: 6000 },
  };
  const track = (id, language, extra = {}) => ({
    id,
    language,
    codec: "eac3",
    channels: 6,
    ...extra,
  });
  const candidate = (id, height, subtitles, why) => ({
    id,
    release: "Fixture.Night." + height + "p.MULTI",
    layer: "ON_DEMAND",
    rd_cached: true,
    size: 12e9,
    duration: 6000,
    height,
    hdr: "sdr",
    audio: [track("1", "en", { default: true }), track("2", "fr")],
    subtitles,
    mode: "direct",
    warnings: [],
    why,
    suggested_audio: track("1", "en"),
    suggested_subtitle: subtitles[0] || null,
  });
  let polls = 0;
  const workflow = () => {
    polls += 1;
    const ready = polls > 1;
    return {
      id: "wf",
      version: ready ? 4 : 3,
      state: ready ? "awaiting_choice" : "preparing",
      media_id: "film",
      source_total: 12,
      suggestion_progress: { checked: ready ? 3 : 1, total: 3 },
      choice_set: ready
        ? {
            id: "set",
            candidates: [
              candidate(
                "best",
                1080,
                [{ id: "10", language: "fr", codec: "subrip" }],
                ["original audio", "French subtitles in the file"],
              ),
              candidate("sharper", 2160, [], ["original audio", "no subtitles in the file"]),
            ],
          }
        : { candidates: [] },
    };
  };
  await page.route(/\/api\/v1\/cinema\//, async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname.replace("/api/v1/cinema", "");
    if (path.endsWith("/poster")) return route.fulfill({ body: poster, contentType: "image/png" });
    if (request.method() !== "GET") {
      writes.push({ path, body: request.postDataJSON() });
      if (path === "/operations/discover")
        return route.fulfill({ json: { operation_id: "op", status: "accepted" } });
      if (path === "/workflows/wf/launch")
        // The screen is busy the first time: the card asks before replacing it.
        return route.fulfill({
          json: request.postDataJSON().replace
            ? { id: "wf", state: "command_sent", version: 5 }
            : { id: "wf", state: "awaiting_playback_confirmation", version: 5 },
        });
      return route.fulfill({ json: { status: "completed" } });
    }
    const json =
      path === "/shelves"
        ? {
            continue: [
              { ...film, media_id: "film", action: "resume", position: 4416, duration: 6000 },
              {
                id: "show",
                media_id: "show",
                title: "Fixture Show",
                series_title: "Fixture Show",
                action: "next",
                season: 1,
                episode: 3,
                poster: film.poster,
              },
            ],
            watchlist: [{ ...film, media_id: "film" }],
            recent: [],
          }
        : path === "/catalogs"
          ? { items: [{ id: "top", name: "Popular", genres: ["Drama", "Comedy"] }] }
          : path === "/browse"
            ? {
                items: Array.from({ length: 12 }, (_, i) => ({
                  ...film,
                  id: "b" + i,
                  title: "Browse " + i,
                })),
                next_offset: 12,
              }
            : path === "/titles/film"
              ? film
              : path === "/devices"
                ? {
                    items: [
                      {
                        id: "tv",
                        name: "Living-room TV",
                        adapter: "cast",
                        state: "idle",
                        version: 1,
                      },
                    ],
                  }
                : path === "/preferences"
                  ? { preferred_device: "tv" }
                  : path === "/operations/op"
                    ? { operation_id: "op", status: "completed", workflow_id: "wf" }
                    : path === "/workflows/wf"
                      ? workflow()
                      : { items: [] };
    await route.fulfill({ json });
  });
  await page.goto(base + "/watch");
  await page.getByRole("list", { name: "Your picks" }).waitFor();
  await page.getByText("Next · S1E3", { exact: true }).waitFor();
  await page.screenshot({ path: "evidence/latest/watch-home-phone.png", fullPage: true });

  await page.getByRole("list", { name: "Your picks" }).getByRole("listitem").first().click();
  const sheet = page.getByRole("dialog", { name: "Fixture Night" });
  const card = sheet.getByRole("region", { name: "Tonight" });
  await card.getByText(/^Checking versions for your TV… 1\/3/).waitFor();
  const play = card.getByRole("button", { name: "Play on the TV", exact: true });
  assert(await play.isDisabled(), "no launch before the check is done");
  await card.getByText("Resume at 1:13:36", { exact: true }).waitFor();
  await card.getByText("French · in the file", { exact: false }).waitFor({ timeout: 10000 });
  assert(await play.isEnabled());
  // Or on this device: VLC streams the chosen version as it is, nothing is kept.
  assert(await card.getByRole("button", { name: /VLC/ }).isVisible());
  assert(await card.getByRole("button", { name: "Copy a link for a player" }).isVisible());
  await card.screenshot({ path: "evidence/latest/watch-tonight-card.png" });
  assert.equal(writes.filter((w) => w.path.endsWith("/launch")).length, 0, "never auto-launch");
  assert.equal(writes.find((w) => w.path === "/operations/discover").body.suggest, true);
  await page.screenshot({ path: "evidence/latest/watch-tonight-phone.png", fullPage: false });

  // A sheet opened from a sheet: Escape (Android's back) closes only the inner one.
  await card.getByRole("button", { name: /^Version/ }).click();
  const versions = page.getByRole("dialog", { name: "Version" });
  await versions.waitFor();
  await page.keyboard.press("Escape");
  await versions.waitFor({ state: "detached" });
  assert(await sheet.isVisible(), "Escape in the Version sheet keeps the film sheet open");

  // Change the version: the 4K one has no subtitles, so the card follows.
  await card.getByRole("button", { name: /^Version/ }).click();
  await versions.getByText("original audio · no subtitles in the file", { exact: true }).waitFor();
  await versions.getByRole("button", { name: /4K/ }).click();
  await card.getByRole("button", { name: /^Subtitles\s*None/ }).waitFor();
  // Back to the suggestion, then a custom start time.
  await card.getByRole("button", { name: /^Version/ }).click();
  await page
    .getByRole("dialog", { name: "Version" })
    .getByRole("button", { name: /1080p/ })
    .click();
  await card.getByRole("button", { name: /^Start/ }).click();
  const start = page.getByRole("dialog", { name: "Start" });
  await start.getByLabel("Start time").fill("0:42:00");
  await start.getByRole("button", { name: "Use this time" }).click();
  await card.getByText("Start at 42:00", { exact: true }).waitFor();
  await play.click();
  // The question below the fold scrolls into view with its answer focused.
  const replace = card.getByRole("button", { name: "Replace", exact: true });
  await replace.waitFor();
  await page.waitForFunction(() => document.activeElement?.textContent === "Replace");
  let box = null; // a smooth scroll: give it a moment
  await until(async () => {
    box = await replace.boundingBox();
    return box && box.y >= 0 && box.y + box.height <= 844;
  }, 2000);
  assert(
    box && box.y >= 0 && box.y + box.height <= 844,
    "Replace is on screen " + JSON.stringify(box),
  );
  await replace.click();
  await page.getByText("Sending Fixture Night to Living-room TV…", { exact: true }).waitFor();
  const launch = writes.find((w) => w.path === "/workflows/wf/launch").body;
  assert.deepEqual(
    [
      launch.source_id,
      launch.device_id,
      launch.audio_track,
      launch.subtitle_track,
      launch.position,
    ],
    ["best", "tv", "1", "10", 2520],
  );
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(base + "/watch");
  await page.getByRole("heading", { name: "Your picks" }).waitFor();
  await page.screenshot({ path: "evidence/latest/watch-home-desktop.png" });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS shelves, checked suggestion, no auto-launch, version/start changes, replace shown in view, exact launch",
  );
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
