// Finishing pass: Nox presets send their id (code presets work without AI), clear speech
// is sent straight away, the stats board renders, history filters by person, tasks finish
// in one tap and a message carries a linked file.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { until } = require("./session.cjs");
(async () => {
  const browser = await chromium.launch({
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
  });
  const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      permissions: ["microphone"],
    }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    errors = [],
    chats = [],
    histories = [],
    actions = [],
    messages = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const people = {
    items: [
      { id: "person-one", name: "Camille", avatar: "crest" },
      { id: "person-two", name: "Max", avatar: "crest" },
    ],
  };
  await page.route("**/api/v1/people", (r) => r.fulfill({ json: people }));
  await page.route("**/api/v1/assistant/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    if (path.endsWith("/voice"))
      return route.fulfill({
        json: { text: "Mets du jazz", language: "fr", duration: 2, confident: true },
      });
    if (path.endsWith("/chat")) {
      chats.push(request.postDataJSON());
      return route.fulfill({ json: { status: "completed", reply: "OK", cards: [] } });
    }
    if (path.endsWith("/conversations") && request.method() === "POST")
      return route.fulfill({ json: { id: "thread-" + chats.length } });
    if (path.endsWith("/status"))
      // No AI configured: the code presets still work, the conversation one waits.
      return route.fulfill({ json: { actor_id: "fixture", available: false } });
    return route.fulfill({ json: { items: [], messages: [], next_offset: null } });
  });

  // Presets
  await page.goto(base + "/assistant");
  const favourites = page.getByRole("button", { name: "Play our favourite songs" });
  await favourites.waitFor();
  assert(await page.getByRole("button", { name: "Help me find something to watch" }).isDisabled());
  await favourites.click();
  await until(() => chats.length);
  assert.equal(chats[0]?.preset, "favorites", JSON.stringify(chats));
  await page.screenshot({ path: "evidence/latest/tweak-presets-phone.png", fullPage: true });

  // Clear speech goes straight to Nox, marked as spoken.
  await page.route("**/api/v1/assistant/status*", (r) =>
    r.fulfill({ json: { actor_id: "fixture", available: true } }),
  );
  await page.route("**/api/v1/assistant/voice/status", (r) =>
    r.fulfill({ json: { available: true, device: "cpu" } }),
  );
  await page.goto(base + "/assistant");
  await page.getByRole("button", { name: "Talk to Nox" }).click();
  await page.waitForTimeout(900);
  await page.getByRole("button", { name: "Stop and use what I said" }).click();
  await until(() => chats.some((c) => c.source === "voice"));
  const spoken = chats.find((c) => c.source === "voice");
  assert.equal(spoken?.message, "Mets du jazz", JSON.stringify(chats));

  // House stats
  await page.route("**/api/v1/stats/house", (r) =>
    r.fulfill({
      json: {
        music: {
          plays: 120,
          hours: 7.5,
          songs: 80,
          week: 30,
          last_week: 12,
          top_songs: [{ title: "Hier encore", artist: "Aznavour", plays: 9, art: null }],
          djs: [
            { id: "person-one", name: "Camille", avatar: "crest", plays: 70 },
            { id: "person-two", name: "Max", avatar: "crest", plays: 50 },
          ],
          genres: [
            { name: "chanson", seconds: 18000, plays: 60 },
            { name: "jazz", seconds: 9000, plays: 4 },
          ],
          hours_of_day: Array.from({ length: 24 }, (_, h) => h),
        },
        titles: [
          { key: "dj", person: people.items[0], value: 70, stars: 1 },
          {
            key: "marathon",
            person: people.items[1],
            value: 180,
            stars: 3,
            song: "A very long relaxing mix with a title that never seems to end at all",
          },
        ],
        week: [{ key: "dj", person: people.items[1], value: 12, stars: 0 }],
        you: { holds: ["dj"], next: { key: "explorer", n: 3 } },
        movies: {
          month: {
            finished: 3,
            episodes: 5,
            hours: 9.5,
            kinds: { film: 5, series: 3, anime: 1.5 },
            genres: [{ name: "Drama", seconds: 20000 }],
          },
          ever: { finished: 0, episodes: 0, hours: 0, kinds: {}, genres: [] },
        },
      },
    }),
  );
  // The numbers live in House → Numbers (Home links there).
  await page.goto(base + "/house?tab=numbers");
  await page.getByText("The house in numbers").waitFor();
  // Music first: genres by time listened, radio included.
  await page.getByText("Hier encore").waitFor();
  await page.locator(".stats__genres").getByText("5 h", { exact: true }).waitFor();
  // Films & series: this month split into films, series and anime.
  await page.locator(".ds-segmented label", { hasText: "Films & series" }).click();
  await page.getByText("Films, series or anime").waitFor();
  await page.locator(".ds-segmented label", { hasText: "All time" }).click();
  await page.getByText("Watch a film and it shows up here.").waitFor();
  // House titles: this week first (the board changes hands); All time, the long-run leaders.
  await page.locator(".ds-segmented label", { hasText: "House titles" }).click();
  await page.locator(".stats__titles").getByText("Max").waitFor();
  await page.locator(".ds-segmented label", { hasText: "All time" }).click();
  await page.locator(".stats__titles").getByText("Camille").waitFor();
  await page.getByText("Head DJ").first().waitFor();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.locator(".stats").screenshot({ path: "evidence/latest/tweak-stats-phone.png" });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(300);
  assert(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    "the home board fits a wide screen",
  );
  await page.setViewportSize({ width: 390, height: 844 });

  // History by person
  await page.route("**/api/v1/music/history*", (r) => {
    histories.push(r.request().url());
    return r.fulfill({ json: { items: [], next_offset: null } });
  });
  await page.goto(base + "/listen");
  // A song opened from a mix is that one song, not a playlist.
  const field = page.getByLabel("Search music", { exact: true });
  await field.fill("https://www.youtube.com/watch?v=8WW7uqLRPSg&list=RD8WW7uqLRPSg&start_radio=1");
  assert.equal(await page.getByRole("button", { name: "Preview playlist" }).count(), 0);
  await field.fill("https://www.youtube.com/playlist?list=PLabcdefghijk");
  await page.getByRole("button", { name: "Preview playlist" }).waitFor();
  await field.fill("");
  await page.getByRole("button", { name: "History" }).click();
  await page.getByLabel("Played by").selectOption({ label: "Max" });
  for (let i = 0; i < 20 && !histories.some((u) => u.includes("by=person-two")); i++)
    await new Promise((r) => setTimeout(r, 100));
  assert(
    histories.some((u) => u.includes("by=person-two")),
    histories.join("\n"),
  );

  // One-tap task completion
  await page.route("**/api/v1/household/tasks**", (r) => {
    if (r.request().method() === "POST") {
      actions.push(r.request().postDataJSON());
      return r.fulfill({ json: { status: "completed" } });
    }
    return r.fulfill({
      json: {
        items: [
          {
            id: "task-1",
            version: 1,
            owner_id: "person-one",
            created_at: "2026-09-23T10:00:00",
            data: { title: "Take out the bins", status: "open", private: true },
          },
        ],
      },
    });
  });
  await page.goto(base + "/house?tab=tasks");
  await page.getByText("Private", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Mark done · Take out the bins" }).click();
  await page.getByRole("button", { name: "Yes, done" }).click(); // ✓ asks once
  for (let i = 0; i < 20 && !actions.length; i++) await new Promise((r) => setTimeout(r, 100));
  assert.equal(actions[0]?.action, "complete");

  // A message carries a linked file.
  await page.route("**/api/v1/files?scope=*", (r) =>
    r.fulfill({
      json: r.request().url().includes("scope=personal")
        ? { items: [{ id: "file-1", name: "plan.pdf", scope: "personal", is_folder: false }] }
        : { items: [] },
    }),
  );
  await page.route("**/api/v1/files/file-1/info", (r) =>
    r.fulfill({ json: { id: "file-1", name: "plan.pdf", size: 2048 } }),
  );
  await page.route("**/api/v1/household/messages", (r) => {
    if (r.request().method() === "POST") {
      messages.push(r.request().postDataJSON());
      return r.fulfill({ json: { id: "m1" } });
    }
    return r.fulfill({ json: { items: [] } });
  });
  await page.route("**/api/v1/household/conversations", (r) => r.fulfill({ json: { items: [] } }));
  await page.goto(base + "/inbox");
  await page.getByRole("button", { name: "New message" }).click();
  await page.getByLabel("Message", { exact: true }).fill("Here is the plan");
  await page.getByRole("button", { name: "Link a file" }).click();
  await page.getByRole("button", { name: /plan\.pdf/ }).click();
  await page.getByRole("button", { name: "Max", exact: true }).click(); // a person chip
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page.getByLabel("Message", { exact: true }).waitFor({ state: "detached" });
  assert.deepEqual(messages[0].data.attachments, ["file-1"]);
  assert.deepEqual(messages[0].data.recipient_ids, ["person-two"]);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/tweak-inbox-phone.png", fullPage: true });

  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS presets, voice auto-send, stats, history by person, task check, message file link",
  );
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
