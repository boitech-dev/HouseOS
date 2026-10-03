// Watch discovery: this week's collections with "See all", the Filters panel (themes, awards,
// a person, sort) with removable chips and results that grow, and a title's "More like this"
// and director chip. Real isolated login; every Cinema read is intercepted.
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
    explored = [];
  let filtered = false; // true once the page shows filter results
  page.on("pageerror", (e) => errors.push(e.message));
  const poster = fs.readFileSync(__dirname + "/../public/art/tv-bezel.png");
  const title = (id, extra = {}) => ({
    id,
    title: "Title " + id,
    kind: "movie",
    year: 1999,
    poster: "/api/v1/cinema/titles/" + id + "/poster",
    ...extra,
  });
  await page.route(/\/api\/v1\/cinema\//, async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname.replace("/api/v1/cinema", "");
    if (path.endsWith("/poster")) return route.fulfill({ body: poster, contentType: "image/png" });
    if (route.request().method() !== "GET") return route.fulfill({ json: { status: "completed" } });
    let json = { items: [] };
    if (path === "/collections")
      json = {
        items: [
          {
            key: "zombies",
            title: "Zombie night",
            name: null,
            group: "niche",
            total: 30,
            sort: "known",
            filters: { tag: ["zombies"] },
            query: { tag: "zombies" },
          },
        ],
      };
    else if (path === "/for-you") json = { items: [title("you1"), title("you2")], based_on: 2 };
    else if (path === "/explore/facets")
      json = {
        ready: true,
        genres: ["Horror", "Comedy"],
        tags: [
          { key: "zombies", label: "Zombies" },
          { key: "heist", label: "Heists" },
        ],
        awards: [{ key: "palme-dor", label: "Palme d'Or" }],
        years: [1920, 2026],
        people_label: "Director or actor",
      };
    else if (path === "/explore/people") json = { items: ["Ada Director"] };
    else if (path === "/explore") {
      explored.push(url.search);
      const offset = Number(url.searchParams.get("offset") || 0);
      // The zombie row's own titles are z…, everything else e…
      const letter = url.searchParams.get("tag") === "zombies" && !filtered ? "z" : "e";
      json = {
        items: Array.from({ length: 24 }, (_, i) => title(letter + (offset + i))),
        total: 30,
        next_offset: offset ? null : 24,
      };
    } else if (path === "/titles/z0")
      json = { ...title("z0"), director: ["Ada Director"], cast: ["Bo Actor"], genres: ["Horror"] };
    else if (path === "/titles/z0/similar")
      json = { items: [title("like1"), title("like2")], franchise: [], source: "themes" };
    await route.fulfill({ json });
  });

  await page.goto(base + "/watch");
  // A collection row, and "See all" turns it into filters with results.
  // Rows: Pick up (filled up to nine with recommendations), every film (endless, sideways),
  // then the collections.
  await page.getByRole("list", { name: "All films" }).waitFor();
  await page.getByRole("list", { name: "Your picks" }).getByText("For you").first().waitFor();
  await page.screenshot({ path: "evidence/latest/watch-rows-phone.png" });
  const zombies = page.getByRole("list", { name: "Zombie night" });
  await zombies.waitFor();
  // A row keeps loading sideways: its 24th title brings the next page.
  await zombies.getByText("Title z23", { exact: true }).scrollIntoViewIfNeeded();
  await zombies.getByText("Title z29", { exact: true }).waitFor({ timeout: 5000 });
  await page.getByRole("button", { name: "See all · Zombie night" }).click();
  // "See all": the row as a page of its own, growing as you scroll; Back returns to the rows.
  await page.getByRole("heading", { name: "Zombie night" }).waitFor();
  assert(page.url().includes("shelf="));
  const all = page.getByRole("list", { name: "Zombie night" });
  await all.getByText("Title z23", { exact: true }).scrollIntoViewIfNeeded();
  await all.getByText("Title z29", { exact: true }).waitFor({ timeout: 5000 });
  await page.screenshot({ path: "evidence/latest/watch-see-all-phone.png" });
  await page.goBack();
  await page.getByRole("list", { name: "All films" }).waitFor();
  assert(!page.url().includes("shelf="));
  filtered = true;

  // More filters: an award and a theme; sort by newest in the bar; each change asks again.
  await page.locator(".watch-filter-toggle").click();
  const panel = page.locator(".watch-filters");
  await panel.getByLabel("Award").selectOption("palme-dor");
  await panel.getByRole("button", { name: "Heists", exact: true }).click();
  await page.getByLabel("Sort").selectOption("newest");
  await until(() => explored.some((q) => q.includes("sort=newest")));
  await page
    .locator(".watch-filters")
    .screenshot({ path: "evidence/latest/watch-filters-phone.png" });
  const last = new URLSearchParams(explored.at(-1));
  assert.equal(last.get("award"), "palme-dor");
  assert.equal(last.get("tag"), "heist");
  // Results keep coming while scrolling.
  await page.getByText("Title e23", { exact: true }).scrollIntoViewIfNeeded();
  await page.getByText("Title e29", { exact: true }).waitFor({ timeout: 5000 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/watch-explore-phone.png" });
  await page.getByRole("button", { name: "Clear all" }).click();
  filtered = false;
  await page.getByRole("list", { name: "Zombie night" }).waitFor();

  // A title: "More like this", and its director opens everything they made.
  await page
    .getByRole("list", { name: "Zombie night" })
    .getByRole("button", { name: /Title z0/ })
    .click();
  const sheet = page.getByRole("dialog", { name: "Title z0" });
  await sheet.getByRole("list", { name: "More like this" }).waitFor();
  await sheet.getByText("Chosen by shared themes, genres and people.").waitFor();
  await sheet.getByRole("button", { name: "Ada Director" }).click();
  await page.getByRole("button", { name: "Remove Ada Director" }).waitFor();
  assert(explored.at(-1).includes("person=Ada+Director"));
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS collections + See all, filters and chips, growing results, more like this, person",
  );
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
