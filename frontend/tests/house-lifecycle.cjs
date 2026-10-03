const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { until } = require("./session.cjs");
// Tasks finish (✓ then confirm) into Done and come back with Reopen; Home finishes tasks and
// ticks groceries in place; events can be removed; conversations reopen and reply; the
// Recovery tab survives a compact backup date; the library sends its filters.
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const me = await (await context.request.get(base + "/api/v1/auth/me")).json();
  const headers = { Origin: base, "X-CSRF-Token": me.csrf_token };
  const stamp = Date.now();
  const add = async (kind, data) =>
    (
      await context.request.post(base + "/api/v1/household/" + kind, {
        headers,
        data: { data, idempotency_key: "life-" + kind + stamp + Math.random() },
      })
    ).json();
  // This test's own tasks from earlier runs (a run that failed halfway leaves them open): gone
  // first, so Home's short list shows this run's task.
  const sweep = async () => {
    const open = await (
      await context.request.get(base + "/api/v1/household/tasks?state=open&limit=200")
    ).json();
    for (const task of open.items || [])
      if (/^(Inline|Lifecycle) task \d+$/.test(task.data.title || ""))
        await context.request.delete(
          base + "/api/v1/household/tasks/" + task.id + "?version=" + task.version,
          { headers },
        );
  };
  await sweep();
  const page = await context.newPage();
  page.on("dialog", (dialog) => dialog.accept());
  const crashes = [];
  page.on("pageerror", (e) => crashes.push(e.message));

  // House: a task added inline in one line (no dialog), due tomorrow.
  const inline = "Inline task " + stamp;
  await page.goto(base + "/house?tab=tasks");
  await page.getByLabel("New task", { exact: true }).fill(inline);
  await page.getByRole("button", { name: "Tomorrow", exact: true }).click();
  await page.locator(".task-composer").getByRole("button", { name: "Add", exact: true }).click();
  await page.locator(".ds-row", { hasText: inline }).waitFor();
  assert.equal(await page.getByRole("dialog").count(), 0, "no popup to add a task");

  // House: ✓, confirm, Done view, Reopen.
  const title = "Lifecycle task " + stamp;
  await add("tasks", { title });
  await page.goto(base + "/house?tab=tasks");
  const row = page.locator(".ds-row", { hasText: title });
  // An open task's control is an empty circle: no tick until it is asked.
  const check = row.getByRole("button", { name: "Mark done · " + title });
  await check.waitFor();
  assert.equal(await check.locator(".ds-icon").isVisible(), false, "open task shows no tick");
  await check.click();
  await row.getByRole("button", { name: "Yes, done" }).click();
  await row.waitFor({ state: "detached" });
  await page.locator(".ds-segmented label", { hasText: "Done" }).click();
  await row.getByRole("button", { name: "Reopen" }).click();
  await row.waitFor({ state: "detached" });
  await page.locator(".ds-segmented label", { hasText: "To do" }).click();
  await row.waitFor();
  assert.equal(await row.getByRole("button", { name: "Decline assignment" }).count(), 0);

  // Home: the same task finished in place (Today), a grocery ticked in place (Groceries).
  const milk = "Lifecycle milk " + stamp;
  await add("groceries", { label: milk });
  await page.goto(base + "/");
  const today = page.locator(".home-today");
  await today.getByRole("button", { name: "Mark done · " + title }).click();
  await today.getByRole("button", { name: "Yes, done" }).click();
  await today.getByText(title).waitFor({ state: "detached" });
  const groceries = page.locator(".home-groceries");
  await groceries.getByLabel("Bought · " + milk).check();
  await groceries.getByText(milk, { exact: true }).waitFor({ state: "detached" });

  // Calendar: an event removed from the agenda list.
  const day = new Date().toISOString().slice(0, 10);
  const next = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  const party = "Lifecycle party " + stamp;
  await add("calendar", { title: party, all_day: true, start: day, end: next });
  // A phone's month shows marks (not buttons): each control there has a name and the day opens it.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(base + "/house?tab=calendar");
  await page.locator(".house-calendar__mark").first().waitFor();
  assert.equal(await page.locator(".house-calendar__event:visible").count(), 0);
  const unnamed = await page
    .locator(".house-calendar button")
    .evaluateAll((all) =>
      all.filter(
        (b) => b.offsetParent && !(b.getAttribute("aria-label") || b.textContent || "").trim(),
      ),
    );
  assert.equal(unnamed.length, 0, "every calendar button has a name");
  // The current tab of House's strip is in view (once the web fonts have given the tabs their width).
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(100);
  const current = await page.locator(".ds-subnav [aria-current]").boundingBox();
  assert(
    current && current.x >= 0 && current.x + current.width <= 390,
    "Calendar tab in view: " + JSON.stringify(current),
  );
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(base + "/house?tab=calendar");
  await page.getByLabel("Calendar view").selectOption("list");
  const event = page.locator(".ds-row", { hasText: party });
  await event.getByRole("button", { name: "More · " + party }).click();
  await event.getByRole("menuitem", { name: "Remove item" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove", exact: true }).click();
  await event.waitFor({ state: "detached" });

  // Messages: a conversation reopens, pages back and takes a reply.
  const people = await (await context.request.get(base + "/api/v1/people")).json();
  const other = (Array.isArray(people) ? people : people.items).find((p) => p.id !== me.user.id);
  assert(other, "the test house needs a second person");
  {
    await add("messages", { body: "Lifecycle hello " + stamp, recipient_ids: [other.id] });
    await page.goto(base + "/inbox");
    await page.locator(".inbox-list .ds-row__main", { hasText: other.name }).first().click();
    await page
      .locator(".inbox-thread")
      .getByText("Lifecycle hello " + stamp)
      .waitFor();
    assert.match(page.url(), /\/inbox\?with=/);
    await page.getByLabel("Reply").fill("Lifecycle reply " + stamp);
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await page
      .locator(".inbox-thread")
      .getByText("Lifecycle reply " + stamp)
      .waitFor();
    await page.reload();
    await page
      .locator(".inbox-thread")
      .getByText("Lifecycle reply " + stamp)
      .waitFor();
    // New message: the composer opens with its first field focused.
    await page.getByRole("button", { name: "New message", exact: true }).click();
    await page.waitForFunction(() => !!document.activeElement?.closest("#inbox-new"));
  }

  // Control Room → Recovery with the backup script's compact date.
  await page.route("**/api/v1/admin/recovery", (route) =>
    route.fulfill({
      json: { container: false, created_at: "20260925T021500Z", retention: "30 days" },
    }),
  );
  await page.goto(base + "/control?tab=recovery");
  await page.getByText("Last backup:").waitFor();

  // Files: the library sends sort, genre and type.
  const asked = [];
  await page.route("**/api/v1/files/library?**", (route) => {
    asked.push(route.request().url());
    return route.fulfill({
      json: {
        items: [],
        total: 0,
        next_offset: null,
        facets: {
          genres: [
            { genre: "Crime", count: 2 },
            { genre: "Sci-Fi", count: 1 },
          ],
          types: { film: 2, anime: 1 },
          people: {},
        },
      },
    });
  });
  await page.goto(base + "/files");
  await page.getByRole("button", { name: "Films & series" }).click();
  await page.getByLabel("Sort").selectOption("year");
  await page
    .getByRole("group", { name: "Type" })
    .getByRole("button", { name: /^Anime/ })
    .click();
  await page
    .getByRole("group", { name: "Genre" })
    .getByRole("button", { name: /^Crime/ })
    .click();
  const filtered = (u) =>
    u.includes("sort=year") && u.includes("type=anime") && u.includes("genre=Crime");
  await until(() => asked.some(filtered));
  assert(asked.some(filtered), asked.join("\n"));
  assert.deepEqual(crashes, []);
  await page.screenshot({ path: "evidence/latest/house-lifecycle.png" });
  await sweep();
  await browser.close();
  console.log("tasks, home, calendar, conversations, recovery and library filters work");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
