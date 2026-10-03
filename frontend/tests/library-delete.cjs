const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
// Files → House music / Films: whoever kept a song or film deletes it after one confirmation;
// someone else's has no delete button. The API is mocked.
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [],
    deleted = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const song = (id, title, mine) => ({
    id,
    title,
    version: 2,
    can_delete: mine,
    genre: "rock",
    plays: 1,
    played_by: [],
    size: 1000,
    download: "/api/v1/files/library/music/" + id + "/download",
    source_url: "https://www.youtube.com/watch?v=" + id,
  });
  await page.route("**/api/v1/files/library/music/*?version=*", (route) => {
    deleted.push(new URL(route.request().url()).pathname.split("/").pop());
    return route.fulfill({ json: { status: "completed" } });
  });
  await page.route(/\/api\/v1\/files\/library\?/, (route) =>
    route.fulfill({
      json: {
        items: [song("mine", "My kept song", true), song("theirs", "Their kept song", false)],
        total: 2,
        facets: { genres: [], types: [], people: [] },
        next_offset: null,
      },
    }),
  );
  await page.goto(base + "/files");
  await page.getByRole("button", { name: "House music" }).click();
  await page.getByText("My kept song").waitFor();
  assert.equal(await page.getByRole("button", { name: "Delete · Their kept song" }).count(), 0);
  await page.getByRole("button", { name: "Delete · My kept song" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByText("My kept song", { exact: true }).waitFor({ state: "detached" });
  assert.deepEqual(deleted, ["mine"]);
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS delete what you kept, after a confirmation; others' stay");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
