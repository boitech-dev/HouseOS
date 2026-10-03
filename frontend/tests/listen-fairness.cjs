// Listen: fair turns, play-next, shuffle, live radio approval/renewal, long playlist import.
// Real isolated login; every music read/write is intercepted, so nothing plays.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  const me = (await (await require("./session.cjs")(context, base)).json()).user;
  const page = await context.newPage(),
    errors = [],
    writes = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const mine = { id: me.id, name: me.name, avatar: "bat" },
    camille = { id: "camille", name: "Camille", avatar: "rose" };
  const song = (id, who, extra = {}) => ({
    id,
    title: "Song " + id,
    owner_id: who.id,
    requester: who,
    source_url: "https://soundcloud.com/fixture/" + id,
    status: "ready",
    downloaded: true,
    duration: 200,
    ...extra,
  });
  const live = Date.now() / 1000 + 600;
  await page.route(/\/api\/v1\/music(?:\/|\?|$)/, async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname.slice("/api/v1/music".length);
    let data = { items: [] };
    if (request.method() !== "GET") {
      writes.push({ path, body: request.postDataJSON() });
      if (path === "/playlists/preview")
        data = {
          confirmation_id: "pl-1",
          title: "Long fixture playlist",
          total: 120,
          items: Array.from({ length: 50 }, (_, i) => ({ title: "Listed " + i })),
        };
      else if (path === "/playlists/pl-1/confirm")
        data = { status: "running", operation_id: "pl-1", added: 50, total: 120 };
      else data = { status: "completed" };
    } else if (!path)
      data = {
        version: 9,
        fair: true,
        current_id: "radio",
        volume: 40,
        items: [
          song("radio", camille, {
            title: "FIP",
            is_live: true,
            status: "awaiting_confirmation",
            error_code: "LIVE_STREAM_REQUIRES_APPROVAL",
            requires_approval: true,
            live_until: live,
          }),
          song("pinned", camille, { pinned: true }),
          song("c1", camille, { round: 1 }),
          song("m1", mine, { round: 1 }),
          song("m2", mine, { round: 2 }),
        ],
        observation: { status: "unavailable" },
      };
    else if (path === "/current/favorite") data = { supported: false };
    await route.fulfill({ json: data });
  });
  await page.goto(base + "/listen");
  const queue = page.locator(".listen-queue");
  await queue.getByText("Song m2", { exact: true }).waitFor();
  assert.deepEqual(
    (await queue.locator(".listen-round").allInnerTexts()).map((x) => x.trim().toLowerCase()),
    ["right after this song", "round 1", "round 2"],
  );

  // A chosen station starts with one tap; the renewal is offered near the end of its hour.
  await page.getByRole("button", { name: "Play this live stream (up to 1 hour)" }).click();
  assert(
    writes.some((w) => w.path === "/queue/radio/approve-live" && w.body.expected_version === 9),
  );
  assert(await page.getByRole("button", { name: "Still listening? One more hour" }).isVisible());

  // On a phone a row keeps "play first", "remove" (on my songs) and "…"; moving one place is in
  // the song's sheet. Anyone moves any waiting song one place, across people too.
  const step = async (song, name) => {
    await queue.getByRole("button", { name: "Song actions · " + song }).click();
    const sheet = page.getByRole("dialog", { name: song });
    const key = sheet.getByRole("button", { name, exact: true });
    if (await key.isDisabled()) {
      await page.keyboard.press("Escape");
      await sheet.waitFor({ state: "hidden" });
      return false;
    }
    await key.click();
    await sheet.waitFor({ state: "hidden" });
    return true;
  };
  assert.equal(await queue.getByRole("button", { name: "Move up · Song m1" }).count(), 0);
  assert(await step("Song m1", "Move up"));
  assert(
    writes.some(
      (w) =>
        w.path === "/queue/m1" && w.body.before_item_id === "c1" && w.body.expected_version === 9,
    ),
    JSON.stringify(writes),
  );
  assert(await step("Song c1", "Move down"));
  assert(writes.some((w) => w.path === "/queue/c1" && w.body.before_item_id === "m2"));
  // The first waiting song can't go higher, the last can't go lower; pinned songs stay put.
  assert(!(await step("Song c1", "Move up")));
  assert(!(await step("Song m2", "Move down")));
  assert((await queue.getByRole("button", { name: "Move up · Song pinned" }).count()) === 0);
  // My songs: play first and remove, one tap each; someone else's only for an admin.
  assert(
    await queue.getByRole("button", { name: "Play next among my songs · Song m2" }).isVisible(),
  );
  assert(await queue.getByRole("button", { name: "Remove from the queue · Song m2" }).isVisible());
  assert.equal(
    await queue.getByRole("button", { name: "Remove from the queue · Song c1" }).count(),
    me.role === "admin" ? 1 : 0,
  );

  // Someone else's song: one veto takes it out; it is not offered on my own songs.
  await queue.getByRole("button", { name: "Song actions · Song c1" }).click();
  const theirs = page.getByRole("dialog", { name: "Song c1" });
  await theirs.getByRole("button", { name: "Veto this song (take it out)" }).click();
  await theirs.waitFor({ state: "hidden" });
  assert(writes.some((w) => w.path === "/queue/c1/veto" && w.body.expected_version === 9));

  // My song moves to the front of my own list.
  await queue.getByRole("button", { name: "Song actions · Song m2" }).click();
  const actions = page.getByRole("dialog", { name: "Song m2" });
  assert((await actions.getByRole("button", { name: /Veto/ }).count()) === 0);
  await actions.getByRole("button", { name: "Play next among my songs" }).click();
  await actions.waitFor({ state: "hidden" });
  assert(
    writes.filter((w) => w.path === "/queue/m2/next" && w.body.expected_version === 9).length === 1,
  );
  await queue.getByRole("button", { name: "Shuffle my songs" }).click();
  assert(writes.some((w) => w.path === "/queue/shuffle-mine"));

  // A long playlist: preview shows the full count, the rest imports in the background.
  await page
    .getByLabel("Search music", { exact: true })
    .fill("https://www.youtube.com/playlist?list=PLfixture000000");
  await page.getByRole("button", { name: "Preview playlist", exact: true }).click();
  const preview = page.getByRole("dialog", { name: "Long fixture playlist" });
  await preview.getByText("…and 70 more", { exact: true }).waitFor();
  await preview.getByRole("button", { name: "Queue 120 songs", exact: true }).click();
  await page.getByText("50 songs added. The rest keeps coming in", { exact: false }).waitFor();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/listen-fairness-phone.png", fullPage: true });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS fair rounds, pinned next, live approval/renewal, free moves, veto, play-next, shuffle, paged import",
  );
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
