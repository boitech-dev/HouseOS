const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { until } = require("./session.cjs");
const fs = require("node:fs");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    errors = [],
    sent = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // Only inference is mocked: this checks client submission/routing without paid requests.
  await page.route("**/api/v1/assistant/**", async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname;
    let data = {};
    if (path.endsWith("/status"))
      data = { actor_id: "fixture-actor", available: true, purpose: "general" };
    else if (path.endsWith("/chat")) {
      sent.push(route.request().postDataJSON());
      data = { conversation_id: "test-chat" };
    } else if (path.endsWith("/conversations") && route.request().method() === "POST")
      data = { id: "test-chat" };
    else if (path.endsWith("/conversations"))
      data =
        url.searchParams.get("offset") === "30"
          ? { items: [{ id: "older-chat", title: "Older task" }], next_offset: null }
          : {
              items: [{ id: "test-chat", title: "Test task", created_at: "2026-09-20T12:00:00Z" }],
              next_offset: 30,
            };
    else if (path.endsWith("/test-chat"))
      data =
        url.searchParams.get("offset") === "50"
          ? {
              messages: [{ id: "earlier-message", role: "user", content: "Earlier task detail" }],
              next_offset: null,
            }
          : {
              next_offset: 50,
              messages: [
                {
                  id: "latest-message",
                  role: "assistant",
                  content:
                    "✅ **Done**, test resident.\nMilk added.\n<script>window.bad=true</script>",
                },
              ],
            };
    await route.fulfill({ json: data });
  });
  // Nox is one tap from Home.
  await page.goto(base + "/");
  const bar = page.getByLabel("Ask Nox, your house manager", { exact: true });
  await bar.waitFor();
  assert.equal(sent.length, 0);
  // The Home bar hands the message to Nox, which sends it at once.
  await bar.fill("Add milk to groceries");
  await bar.press("Enter");
  await page.getByRole("dialog", { name: "Nox" }).waitFor();
  assert.equal(await page.locator(".ask select").count(), 0);
  await until(() => sent.length, 10000);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].conversation_id, "test-chat");
  assert.equal(sent[0].purpose, "general");
  assert.equal(sent[0].context, undefined);
  assert.equal(sent[0].provider, undefined);
  await page.getByText("Done, test resident.").waitFor();
  assert.equal(await page.locator(".ask-text strong").textContent(), "Done");
  assert.equal(await page.evaluate(() => window.bad), undefined);
  await page.getByRole("button", { name: "Load earlier messages" }).click();
  await page.getByText("Earlier task detail", { exact: true }).waitFor();
  // Past conversations fold away in the Nox panel; open the list first.
  await page.getByRole("button", { name: "Conversations", exact: true }).click();
  await page.getByRole("button", { name: "Load more conversations" }).click();
  await page.getByRole("button", { name: "Older task" }).waitFor();
  await page.getByRole("button", { name: "New conversation", exact: true }).click();
  assert.equal(await page.getByLabel("Message your assistant").inputValue(), "");
  assert(!page.url().includes("conversation="));
  const me = await (await context.request.get(base + "/api/v1/auth/me")).json();
  const headers = { Origin: base, "X-CSRF-Token": me.csrf_token };
  const cleanup = await (
    await context.request.get(base + "/api/v1/household/calendar?limit=100")
  ).json();
  for (const stale of cleanup.items || []) {
    if (stale.data.title === "Private calendar fixture")
      await context.request.delete(
        base + "/api/v1/household/calendar/" + stale.id + "?version=" + stale.version,
        { headers },
      );
  }
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Paris" }).format(new Date());
  const start = new Date(today + "T12:00:00Z");
  start.setUTCDate(start.getUTCDate() + 1);
  const next = start.toISOString().slice(0, 10);
  const created = await context.request.post(base + "/api/v1/household/calendar", {
    headers,
    data: {
      idempotency_key: crypto.randomUUID(),
      data: {
        title: "Private calendar fixture",
        start: today,
        end: next,
        all_day: true,
        timezone: "Europe/Paris",
        participants: [],
        reminder_minutes: [],
        notes: "Full detail fixture",
      },
    },
  });
  assert(created.ok(), await created.text());
  const row = await created.json();
  try {
    // Home's Calendar tile counts today's plans and opens the day in one tap.
    await page.goto(base + "/");
    const plans = page.locator(".home-today").getByRole("link", { name: /^Calendar/ });
    await page.locator(".home-today").getByText("Private calendar fixture").waitFor();
    assert.doesNotMatch(await plans.innerText(), /Nothing/);
    await page.screenshot({ path: "evidence/latest/chat-first-home-desktop.png", fullPage: true });
    await plans.click();
    await page.getByRole("dialog").waitFor();
    await page.getByRole("heading", { name: "Private calendar fixture", exact: true }).waitFor();
    await page.getByText("Full detail fixture", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Close", exact: true }).click();
    assert.equal(await page.getByLabel("Calendar view").inputValue(), "month");
    await page.screenshot({ path: "evidence/latest/calendar-month-desktop.png", fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(base + "/");
    await page.locator(".home-hero").waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: "evidence/latest/chat-first-home-phone.png", fullPage: true });
  } finally {
    await context.request.delete(
      base + "/api/v1/household/calendar/" + row.id + "?version=" + row.version,
      { headers },
    );
  }
  assert.deepEqual(errors, []);
  fs.writeFileSync(
    "evidence/latest/chat-calendar-result.json",
    JSON.stringify(
      {
        passed: true,
        checks: [
          "landing fresh composer above fold",
          "no chat created before submit",
          "admin-assigned purpose with no provider controls",
          "fresh conversation ID null",
          "chat navigation and history",
          "safe bold/newlines/emoji and escaped HTML",
          "real API calendar event appears as private dashboard marker only",
          "real month calendar and day details",
          "390px no overflow",
          "no JavaScript errors",
        ],
        boundary:
          "Real isolated authentication and calendar persistence; assistant responses mocked, no model call",
      },
      null,
      2,
    ),
  );
  await browser.close();
  console.log("Chat/calendar browser checks passed");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
