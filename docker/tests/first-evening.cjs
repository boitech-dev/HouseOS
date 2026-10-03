// Release gate: a stranger's first evening with a fresh Docker install, reached only by name
// through HTTPS (like a headless server behind a reverse proxy). Run it from the folder that
// holds docker-compose.yml, after `docker compose up -d --build` on empty volumes:
//   BASE=https://houseos.test:8443 node docker/tests/first-evening.cjs
// It creates the admin, then checks that the address was adopted, every Control Room page
// and room reads in words (no raw codes), the microphone explains itself, and nothing throws.
let playwright;
try {
  playwright = require("playwright");
} catch {
  playwright = require("/usr/lib/node_modules/playwright");
}
const assert = require("node:assert/strict");
const { execSync } = require("node:child_process");
const base = process.env.BASE || "https://houseos.test:8443";
const host = new URL(base).hostname;
const code =
  process.env.SETUP_CODE ||
  execSync("docker compose exec -T api houseos-entrypoint setup-code").toString().split(": ")[1].trim();
// SETTING_NAMES are shown on purpose (they are what you type in .env); other codes are not.
const RAW = /\b(?!HOUSEOS_)[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b/;
(async () => {
  const browser = await playwright.chromium.launch({
    headless: true,
    args: [`--host-resolver-rules=MAP ${host} 127.0.0.1`],
  });
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base + "/");
  await page.getByLabel(/Your name|Ton nom/).fill("First Evening");
  await page.getByLabel(/Username|Nom d.utilisateur|Identifiant/).fill("evening");
  await page.getByLabel(/^Choose a password|^Choisis un mot de passe/).fill("first-evening-password-2026");
  await page.getByLabel(/^Setup code|^Code d/).fill(code);
  await page.getByRole("button", { name: /Set up|Create|Créer|Configurer|Continue|Start/ }).first().click();
  const shell = page.locator(".shell").first();
  await shell.waitFor({ timeout: 20000 });
  const failures = [];
  for (const path of [
    "/control?tab=setup",
    "/control?tab=access",
    "/control?tab=services",
    "/control?tab=speakers",
    "/control?tab=ai",
    "/control?tab=integrations",
    "/control?tab=health",
    "/",
    "/listen",
    "/watch",
    "/house",
    "/files",
    "/assistant",
  ]) {
    await page.goto(base + path);
    await page.waitForTimeout(2000);
    const raw = (await shell.innerText()).match(RAW);
    if (raw) failures.push(`${path} shows ${raw[0]}`);
  }
  // A new owner is welcomed on Home: the house's set-up, one step at a time.
  await page.goto(base + "/");
  await page.getByRole("dialog", { name: /Welcome home|Bienvenue à la maison/ }).waitFor({ timeout: 10000 });
  await page.goto(base + "/control?tab=access");
  // The address used for setup is trusted (waits for the list to load).
  await page.getByText(new URL(base).origin, { exact: true }).first().waitFor({ timeout: 10000 });
  await page.goto(base + "/assistant");
  const mic = page.getByRole("button", { name: /Talk to Nox|Parler à Nox/ }).first();
  await mic.waitFor({ timeout: 10000 }); // shown, with a reason when it can't listen yet
  assert(errors.length === 0, "page errors: " + errors.join("; "));
  assert(failures.length === 0, failures.join("\n"));
  await browser.close();
  console.log("PASS first evening");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
