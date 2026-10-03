// The welcomes, once each: the owner's set-up (the house's theme first, live ✓ from /admin/setup,
// the coding-agent prompt, leaving asks first, reopening from Control Room), a new resident's (profile,
// look, what to know), a TV guest's one screen, "What's new" after an update, and the dot on Nox
// that runs the tour. The owner's setup state and profile flag are mocked.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const { RELEASE, settled, until } = require("./session.cjs");
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const me = await (await require("./session.cjs")(context, base)).json();
  const headers = { Origin: base, "X-CSRF-Token": me.csrf_token };
  const prefs = (data, ctx = context, h = headers) =>
    ctx.request.put(base + "/api/v1/preferences", { headers: h, data });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const dialog = page.locator("dialog[open]").last();
  const title = () => dialog.locator(".ds-sheet__head h2").textContent();
  const next = () => dialog.getByRole("button", { name: "Next", exact: true }).click();
  const noSideScroll = async () =>
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

  // ---- 1. The owner's set-up on a new house ----
  const ready = new Set(["ai"]);
  let dismissed = false;
  await page.route("**/api/v1/admin/setup", (r) =>
    r.fulfill({
      json: {
        container: true,
        steps: ["house", "access", "ai", "speakers", "films", "tv", "invite"].map((key) => ({
          key,
          tab: key,
          state: ready.has(key) ? "done" : "todo",
        })),
        done: 1,
        needed: 6,
      },
    }),
  );
  await page.route("**/api/v1/account/profile", async (r) => {
    if (r.request().method() === "PATCH") dismissed = !!r.request().postDataJSON().welcome_dismissed;
    await r.fulfill({ json: { id: me.id, name: "Ada Night", welcome_dismissed: dismissed } });
  });
  await prefs({ onboarded: "", seen_release: "" });
  await page.goto(base + "/");
  await dialog.waitFor();
  assert.equal(await title(), "Welcome home");
  assert(await dialog.getByText(/, your house is ready\./).isVisible());
  await noSideScroll();
  await dialog.getByRole("button", { name: "Let's set it up" }).click();
  // The theme first: picking one changes the house's look at once.
  assert.equal(await title(), "Pick a theme");
  assert(await dialog.getByRole("radiogroup", { name: "Themes" }).isVisible());
  await next();
  assert.equal(await title(), "Connect an AI");
  assert(await dialog.getByText("Nox is connected and answers.").isVisible());
  await next();
  assert.equal(await title(), "Films and series");
  // The add-on's link is pasted right here; a catalogue opens in a new tab to find one.
  assert(await dialog.getByLabel("Your stream add-on's link").isVisible());
  assert.equal(
    await dialog.getByRole("link", { name: "Browse add-ons" }).getAttribute("target"),
    "_blank",
  );
  // A setting keeps the place: back on Home, the same step.
  await dialog.getByRole("button", { name: "More settings" }).click();
  await page.waitForURL(/\/control\?tab=integrations&open=stream_addon$/);
  await page.goto(base + "/");
  await dialog.waitFor();
  assert.equal(await title(), "Films and series");
  // Leaving asks first; "Leave for now" lasts this session only.
  await page.keyboard.press("Escape");
  const leave = page.getByRole("dialog", { name: "Leave the set-up for now?" });
  await leave.waitFor();
  await leave.getByRole("button", { name: "Leave for now" }).click();
  await page.waitForFunction(() => !document.querySelector("dialog[open]"));
  await page.reload();
  await page.locator(".home-hero").waitFor();
  await page.waitForTimeout(800);
  assert.equal(await page.locator("dialog[open]").count(), 0);
  // Control Room → Setup reopens it; Done on the last step ends it for good.
  await page.goto(base + "/control?tab=setup");
  await page.getByRole("button", { name: "Show the welcome again" }).click();
  await dialog.waitFor();
  assert.equal(await title(), "Welcome home");
  await page.setViewportSize({ width: 1280, height: 860 });
  for (let i = 0; i < 6; i++) await dialog.locator(".journey__foot > button").last().click();
  assert.equal(await title(), "You're set");
  // Your coding agent: a ready prompt that names the folder's own guide.
  await dialog.getByText("Or use your coding agent").click();
  assert.match(await dialog.locator(".journey__prompt").textContent(), /Read AGENTS\.md first/);
  await dialog.getByRole("button", { name: "Done", exact: true }).click();
  await page.waitForFunction(() => !document.querySelector("dialog[open]"));
  assert(dismissed, "the owner's welcome is dismissed on the account");
  assert(await until(async () => (await (await context.request.get(base + "/api/v1/preferences")).json()).onboarded === "admin"));
  await page.unroute("**/api/v1/admin/setup");
  await page.unroute("**/api/v1/account/profile");

  // ---- 2. What's new, once after an update ----
  // A mark above the current release (a pre-release build's) counts as seen: nothing opens.
  await prefs({ seen_release: "9.9" });
  await page.goto(base + "/listen");
  await page.waitForTimeout(2000);
  assert.equal(await page.locator("dialog[open]").count(), 0, "a newer mark shows nothing");
  await prefs({ seen_release: "0.9" });
  await page.goto(base + "/listen");
  await dialog.waitFor();
  assert.equal(await title(), "What's new in HouseOS");
  assert(await dialog.getByText("Any video link on the TV", { exact: true }).isVisible());
  await dialog.getByRole("button", { name: "Got it" }).click();
  await page.waitForFunction(() => !document.querySelector("dialog[open]"));
  assert(await until(async () => (await (await context.request.get(base + "/api/v1/preferences")).json()).seen_release === RELEASE));

  // ---- 3. The dot on Nox: one tap runs the tour, then it's gone ----
  await page.setViewportSize({ width: 390, height: 844 });
  await prefs({ tour_seen: false });
  await page.goto(base + "/");
  const nox = page.locator(".shell__dock").getByRole("button", { name: "Ask Nox · how the house works" });
  await nox.click();
  await page.getByText("Welcome to the house!").first().waitFor();
  assert(await until(async () => (await (await context.request.get(base + "/api/v1/preferences")).json()).tour_seen === true));
  await prefs(settled("admin"));

  // ---- 4. A new resident, and a guest from a TV code ----
  for (const preset of ["roommate", "screen"]) {
    const invite = await (
      await context.request.post(base + "/api/v1/auth/invites", {
        headers,
        data: { preset, expires_hours: 2 },
      })
    ).json();
    const other = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const joined = await other.request.post(base + "/api/v1/auth/redeem", {
      headers: { Origin: base },
      data: {
        token: invite.token,
        username: "welcome_" + preset + "_" + Date.now(),
        name: preset === "screen" ? "Test-only TV guest" : "Test-only new resident",
        password: "Test-only-Welcome-2046",
      },
    });
    assert(joined.ok(), preset + " invite redeemed");
    // The test house speaks French; these checks read English.
    await other.request.patch(base + "/api/v1/account/profile", {
      headers: { Origin: base, "X-CSRF-Token": (await joined.json()).csrf_token },
      data: { language: "en" },
    });
    const p = await other.newPage();
    p.on("pageerror", (e) => errors.push(e.message));
    const d = p.locator("dialog[open]").last();
    await p.goto(base + "/");
    await d.waitFor();
    if (preset === "screen") {
      // One screen: music, and the TV this code allows.
      assert.equal(await d.locator(".ds-sheet__head h2").textContent(), "Welcome, Test-only TV guest!");
      assert(await d.getByText("Watch on the TV").isVisible());
      await d.getByRole("button", { name: "Let's go" }).click();
      await p.getByRole("button", { name: "Pick a film for the TV" }).waitFor();
    } else {
      assert.equal(await d.locator(".ds-sheet__head h2").textContent(), "Welcome home");
      await d.getByRole("button", { name: "Start" }).click();
      await d.getByLabel("Your name").fill("Test-only Robin");
      await d.getByRole("button", { name: "Next", exact: true }).click();
      await d.getByRole("radiogroup", { name: "Themes" }).waitFor();
      await d.getByRole("button", { name: "Next", exact: true }).click();
      assert.equal(await d.locator(".ds-sheet__head h2").textContent(), "Good to know");
      await d.getByRole("button", { name: "Let's go" }).click();
      const profile = await (await other.request.get(base + "/api/v1/account/profile")).json();
      assert.equal(profile.name, "Test-only Robin");
    }
    await p.waitForFunction(() => !document.querySelector("dialog[open]"));
    // Once: not again on the next visit.
    await p.reload();
    await p.waitForTimeout(1000);
    assert.equal(await p.locator("dialog[open]").count(), 0);
    await other.close();
  }
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS the owner's set-up, a resident's and a TV guest's welcomes, What's new and Nox's tour dot, once each");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
