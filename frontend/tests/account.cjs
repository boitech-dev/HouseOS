const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const fs = require("fs");
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const base = "http://127.0.0.1:8893";
  const auth = await require("./session.cjs")(context, base);
  const me = await auth.json();
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base + "/settings?tab=profile", { waitUntil: "domcontentloaded" });
  const profile = page.locator(".ds-settings__detail");
  await profile.getByRole("radio", { name: "Bat", exact: true }).check();
  await profile.getByRole("button", { name: "Save profile", exact: true }).click();
  await page.getByText("Profile saved.", { exact: true }).waitFor();
  // Account metadata shares storage with UI defaults but is not part of their PUT contract.
  await page.goto(base + "/settings?tab=comfort", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByText("Preferences saved.", { exact: true }).waitFor();
  await page.goto(base + "/settings?tab=profile", { waitUntil: "domcontentloaded" });
  const preservedProfile = await (
    await context.request.get(base + "/api/v1/account/profile")
  ).json();
  assert.equal(preservedProfile.avatar, "bat");
  const exported = await context.request.get(base + "/api/v1/account/export");
  assert(exported.ok());
  const data = await exported.json();
  assert.equal(data.complete, true);
  assert.equal(data.account.id, me.user.id);
  assert(!JSON.stringify(data).includes("password_hash"));
  await profile.getByText("Delete my account", { exact: true }).click();
  assert.equal(await profile.getByLabel("Password for deletion preview").count(), 0);
  await profile.getByRole("button", { name: "Review account deletion", exact: true }).click();
  await page.getByRole("dialog", { name: "Review account deletion" }).waitFor();
  await page.keyboard.press("Escape");
  const invitation = await (
    await context.request.post(base + "/api/v1/auth/invites", {
      headers: { Origin: base, "X-CSRF-Token": me.csrf_token },
      data: { preset: "party", expires_hours: 2, membership_hours: 2 },
    })
  ).json();
  const guest = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const redeemed = await guest.request.post(base + "/api/v1/auth/redeem", {
    headers: { Origin: base },
    data: {
      token: invitation.token,
      username: "ui_guest_" + Date.now(),
      name: "Test-only party guest",
      password: "Test-only-Guest-2046",
    },
  });
  assert(redeemed.ok(), "isolated guest invite redemption");
  // Their one-screen welcome is tests/onboarding.cjs's: seen here.
  await guest.request.put(base + "/api/v1/preferences", {
    headers: { Origin: base, "X-CSRF-Token": (await redeemed.json()).csrf_token },
    data: require("./session.cjs").settled("guest"),
  });
  const p = await guest.newPage();
  await p.goto(base, { waitUntil: "domcontentloaded" });
  await p.getByRole("heading", { name: "Écouter", exact: true }).waitFor();
  assert.equal(
    await p.getByRole("heading", { name: "Le mur de la maison", exact: true }).count(),
    0,
  );
  // Guests add and vote; the transport keys belong to residents.
  await p.locator(".listen-deck").waitFor();
  assert.equal(
    await p.locator(".listen-deck").getByRole("button", { name: "Lire", exact: true }).count(),
    0,
  );
  await p.goto(base + "/files", { waitUntil: "domcontentloaded" });
  await p.getByText("Ton invitation ne donne pas accès à cet espace.", { exact: true }).waitFor();
  await p.goto(base + "/settings?tab=profile", { waitUntil: "domcontentloaded" });
  await p.getByRole("heading", { name: "Ton profil", exact: true }).waitFor();
  // A guest has no film choices to make: no Films place in their settings.
  assert.equal(await p.getByRole("button", { name: "Films", exact: true }).count(), 0);
  assert.equal((await guest.request.get(base + "/api/v1/files")).status(), 403);
  assert.equal(errors.length, 0, errors.join(";"));
  fs.writeFileSync(
    "evidence/latest/account-result.json",
    JSON.stringify(
      {
        passed: true,
        checks: [
          "profile avatar save",
          "UI preferences save after profile update preserves account fields",
          "own complete export without password hash",
          "account deletion preview only; not executed",
          "party invite redeem",
          "guest music controls disabled",
          "guest household/private routes unavailable",
          "guest settings restricted",
        ],
        pageErrors: errors,
      },
      null,
      2,
    ),
  );
  await browser.close();
  console.log("PASS own profile/export/delete preview and party guest UI/API isolation");
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
