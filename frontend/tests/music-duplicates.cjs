const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
// Files → House music, for an admin: songs kept twice show as one notice; its sheet keeps the
// chosen one (the others go through the library's own delete, after a confirmation), plays a
// song first, and remembers "Not duplicates". The API is mocked.
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [],
    deleted = [],
    dismissed = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const song = (id, title, uploader, plays, suggested) => ({
    id,
    title,
    uploader,
    duration: 355 + plays,
    size: 8_000_000,
    plays,
    last_played: null,
    kept_at: "2026-09-20T10:00:00",
    source_url: "https://www.youtube.com/watch?v=" + id,
    download: "/api/v1/files/library/music/" + id + "/download",
    version: 2,
    suggested,
    delete: "/files/library/music/" + id + "?version=2",
  });
  let groups = [
    {
      ids: ["official", "topic"],
      songs: [
        song("official", "Queen - Bohemian Rhapsody (Official Video)", "Queen Official", 7, true),
        song("topic", "Bohemian Rhapsody (Remastered 2011)", "Queen - Topic", 1, false),
      ],
    },
    {
      ids: ["halo-a", "halo-b"],
      songs: [
        song("halo-a", "Beyoncé - Halo", "Beyoncé", 3, true),
        song("halo-b", "Beyonce - Halo (Lyrics)", "7clouds", 0, false),
      ],
    },
  ];
  await page.route("**/api/v1/files/library/duplicates", (route) =>
    route.fulfill({ json: { groups, count: groups.length } }),
  );
  await page.route("**/api/v1/files/library/duplicates/dismiss", (route) => {
    const ids = route.request().postDataJSON().ids;
    dismissed.push(ids);
    groups = groups.filter((g) => g.ids.join() !== ids.join());
    return route.fulfill({ json: { status: "completed" } });
  });
  await page.route("**/api/v1/files/library/music/*?version=*", (route) => {
    const id = new URL(route.request().url()).pathname.split("/").pop();
    deleted.push(id);
    groups = groups.filter((g) => !g.ids.includes(id));
    return route.fulfill({ json: { status: "completed" } });
  });
  await page.route("**/api/v1/files/library/music/*/download", (route) =>
    route.fulfill({ status: 404, body: "" }),
  );
  await page.route(/\/api\/v1\/files\/library\?/, (route) =>
    route.fulfill({
      json: {
        items: groups
          .flatMap((g) => g.songs)
          .map((s) => ({ ...s, played_by: [], can_delete: true })),
        total: 4,
        facets: { genres: [], types: [], people: [] },
        next_offset: null,
      },
    }),
  );
  await page.goto(base + "/files");
  await page.getByRole("button", { name: "House music" }).click();
  await page.getByText("Possible duplicates (2)").waitFor();
  await page.getByRole("button", { name: "Review", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Possible duplicates" });
  const row = (title) => sheet.getByRole("listitem").filter({ hasText: title });
  await row("Queen - Bohemian Rhapsody (Official Video)").getByText("Suggested to keep").waitFor();
  // Listen first: one player for the song asked for.
  await sheet.getByRole("button", { name: "Listen · Beyonce - Halo (Lyrics)" }).click();
  assert.equal(await sheet.locator("audio").count(), 1);
  // Keep the official video: the other one goes, after a confirmation.
  await row("Queen - Bohemian Rhapsody (Official Video)")
    .getByRole("button", { name: "Keep this one" })
    .click();
  await page
    .getByRole("dialog")
    .last()
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await row("Bohemian Rhapsody (Remastered 2011)").waitFor({ state: "detached" });
  assert.deepEqual(deleted, ["topic"]);
  // The other pair isn't one song: remembered, and nothing is left to review.
  await sheet.getByRole("button", { name: "Not duplicates" }).click();
  await sheet.getByText("No possible duplicates left.").waitFor();
  assert.deepEqual(dismissed, [["halo-a", "halo-b"]]);
  assert.deepEqual(deleted, ["topic"]);
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS possible duplicates: listen, keep one after a confirmation, not duplicates");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
