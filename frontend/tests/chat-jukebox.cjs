const { chromium } = require("/usr/lib/node_modules/playwright"),
  assert = require("node:assert/strict"),
  fs = require("node:fs");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  for (const path of [
    "/music/history?offset=0&limit=5",
    "/music/current/favorite",
    "/music/saved",
  ]) {
    const response = await context.request.get(base + "/api/v1" + path);
    assert.equal(response.status(), 200);
    const data = await response.json();
    if (path.includes("/history"))
      assert(Array.isArray(data.items) && data.items.length <= 5 && "next_offset" in data);
    else if (path.includes("/favorite")) assert("supported" in data && "favorite" in data);
    else assert(Array.isArray(data));
  }
  const page = await context.newPage(),
    errors = [],
    chats = [],
    musicWrites = [],
    cinemaWrites = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let idle = false,
    favorite = false;
  await page.route("**/api/v1/assistant/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data = {};
    if (path.endsWith("/status"))
      data = { actor_id: "fixture-actor", available: true, purpose: "general" };
    else if (path.endsWith("/chat")) {
      chats.push(route.request().postDataJSON());
      await new Promise((resolve) => setTimeout(resolve, 120));
      data = { conversation_id: "keyboard-chat" };
    } else if (path.endsWith("/conversations") && route.request().method() === "POST")
      data = { id: "keyboard-chat" };
    else if (path.endsWith("/conversations")) data = { items: [], next_offset: null };
    else
      data = {
        messages: [{ id: "keyboard-reply", role: "assistant", content: "Done." }],
        next_offset: null,
      };
    await route.fulfill({ json: data });
  });
  await page.route(/\/api\/v1\/music(?:\/|\?|$)/, async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname.slice("/api/v1/music".length);
    let data = { items: [] };
    if (route.request().method() !== "GET") {
      musicWrites.push({ path, body: route.request().postDataJSON() });
      if (path === "/current/favorite") favorite = true;
      data = { status: "accepted" };
    } else if (!path)
      data = {
        version: 1,
        autoplay_on_add: idle,
        current_id: idle ? null : "current-fixture",
        items: idle
          ? []
          : [
              {
                id: "current-fixture",
                title: "Current fixture track",
                source_url: "https://www.youtube.com/watch?v=fixture0000",
                duration: 180,
                status: "playing",
              },
              ...Array.from({ length: 8 }, (_, i) => ({
                id: "next-" + i,
                title: "Next fixture " + i,
                source_url: "https://www.youtube.com/watch?v=fixture0001",
                status: "ready",
                duration: 180,
              })),
            ],
        observation: { status: "observed", idle, paused: false, position: 12 },
        volume: 25,
      };
    else if (path === "/current/favorite")
      data = {
        item_id: "current-fixture",
        source_url: "https://www.youtube.com/watch?v=fixture0000",
        supported: true,
        favorite,
        saved_id: favorite ? "saved-current" : null,
      };
    else if (path === "/history") {
      const before = url.searchParams.get("before"); // the cursor is "c<next row>" here
      let offset = before ? Number(before.slice(1)) : Number(url.searchParams.get("offset") || 0),
        limit = Number(url.searchParams.get("limit") || 5);
      data = {
        items: Array.from({ length: Math.min(limit, 55 - offset) }, (_, i) => ({
          id: "history-" + (offset + i),
          title: "Previous fixture " + (offset + i),
          source_url: "https://www.youtube.com/watch?v=fixture0002",
          uploader: "Fixture artist",
          requester: { id: "resident-fixture", name: "Camille" },
          played_at: "2026-09-20T12:00:00Z",
          favorite: false,
          favorite_supported: true,
        })),
        next_offset: offset + limit < 55 ? offset + limit : null,
        next_before: offset + limit < 55 ? "c" + (offset + limit) : null,
      };
    }
    await route.fulfill({ json: data });
  });
  await page.route("**/api/v1/cinema/current", (r) =>
    r.fulfill({
      json: {
        current: {
          id: "fixture-movie",
          title: "Fixture movie controls",
          version: 7,
          state: "playing_observed",
          observation: { state: "playing" },
          checkpoint: { position: 120 },
        },
      },
    }),
  );
  await page.route("**/api/v1/cinema/workflows**", async (route) => {
    if (route.request().method() === "POST") {
      cinemaWrites.push(route.request().postDataJSON());
      await route.fulfill({ json: { status: "accepted" } });
    } else
      await route.fulfill({
        json: {
          items: [
            {
              id: "fixture-movie",
              title: "Fixture movie controls",
              version: 7,
              state: "playing_observed",
              observation: { state: "playing" },
              checkpoint: { position: 120 },
            },
          ],
        },
      });
  });
  await page.goto(base + "/assistant");
  const input = page.getByLabel("Message your assistant", { exact: true });
  await input.fill("First line");
  await input.press("Shift+Enter");
  await input.press("KeyX");
  assert.equal(await input.inputValue(), "First line\nx");
  assert.equal(chats.length, 0);
  await input.evaluate((el) =>
    el.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true, isComposing: true }),
    ),
  );
  assert.equal(chats.length, 0);
  await input.evaluate((el) =>
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, keyCode: 229 })),
  );
  assert.equal(chats.length, 0);
  await input.press("Enter");
  await page.keyboard.press("Enter");
  await page.locator(".ask-message[data-role=user]").first().waitFor();
  assert.equal(chats.length, 1);
  assert.equal(chats[0].message, "First line\nx");
  await page.goto(base + "/");
  await page.getByRole("heading", { name: "Current fixture track" }).waitFor();
  // On Home the film is in the Now card: its tile opens the Now sheet and its controls.
  await page.getByRole("button", { name: /^On the TV/ }).click();
  const now = page.getByRole("dialog", { name: "Now playing" });
  await Promise.all([
    page.waitForRequest((r) => r.url().includes("/cinema/workflows/") && r.method() === "POST"),
    now.getByRole("button", { name: "Pause", exact: true }).click(),
  ]);
  await page.keyboard.press("Escape");
  await now.waitFor({ state: "detached" });
  for (let i = 0; i < 30 && !cinemaWrites.length; i++) await page.waitForTimeout(100);
  assert.equal(cinemaWrites[0].action, "pause");
  assert.equal(cinemaWrites[0].version, 7);
  // Home shows the deck and the next three songs.
  assert.equal(await page.locator(".listen-panel .ds-row").count(), 3);
  await Promise.all([
    page.waitForRequest((r) => r.url().endsWith("/current/favorite") && r.method() !== "GET"),
    page.getByRole("button", { name: "Favorite current track", exact: true }).click(),
  ]);
  for (let i = 0; i < 30 && !musicWrites.length; i++) await page.waitForTimeout(100);
  assert.equal(musicWrites[0].path, "/current/favorite");
  assert.equal(musicWrites[0].body.item_id, "current-fixture");
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.locator("main").focus();
  await page.screenshot({ path: "evidence/latest/jukebox-recent-phone.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(base + "/listen");
  const field = page.getByLabel("Search music", { exact: true });
  const add = page.locator(".listen-add__field button");
  assert.equal(await add.innerText(), "Search");
  await field.fill("https://www.youtube.com/watch?v=fixture0003");
  assert.equal(await add.innerText(), "Add to queue");
  await page
    .getByRole("navigation", { name: "Listen" })
    .getByRole("button", { name: "History", exact: true })
    .click();
  const history = page.getByRole("region", { name: "History", exact: true });
  await history.getByText("Previous fixture 29", { exact: true }).waitFor();
  assert.equal(await history.locator(".ds-row").count(), 30);
  assert((await history.locator(".ds-row").first().innerText()).includes("Camille"));
  await history
    .getByRole("button", { name: "Save track · Previous fixture 0", exact: true })
    .click();
  assert(musicWrites.some((r) => r.path === "/saved"));
  // Older songs come as the list scrolls, below the ones already shown.
  await history.getByText("Previous fixture 29", { exact: true }).scrollIntoViewIfNeeded();
  await history.getByText("Previous fixture 54", { exact: true }).waitFor();
  assert.equal(await history.locator(".ds-row").count(), 55);
  idle = true;
  await page.goto(base + "/listen");
  await page.getByLabel("Search music", { exact: true }).fill("https://soundcloud.com/a/b");
  await page.waitForFunction(
    () => document.querySelector(".listen-add__field button")?.textContent === "Play",
  );
  assert.deepEqual(errors, []);
  fs.writeFileSync(
    "evidence/latest/chat-jukebox-result.json",
    JSON.stringify(
      {
        passed: true,
        checks: [
          "Enter submits once",
          "ShiftEnter newline",
          "IME composition and229 never submit",
          "dashboard next5/recent5",
          "exactcurrentfavorite",
          "historyfavorite",
          "fullhistorypagination",
          "Playidle/Addqueueactive",
          "dashboard Cinema exact workflow/version control",
          "390px no overflow",
        ],
        boundary:
          "Real isolated login and music endpoint schemas; mocked assistant/music interaction contracts, no inference or physical playback",
      },
      null,
      2,
    ),
  );
  await browser.close();
  console.log("PASS chat keyboard and jukebox history/favorites UX");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
