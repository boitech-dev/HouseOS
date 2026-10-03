// Test-only session reuse. Never export this protected runtime state into the repo.
const fs = require("node:fs");
// Where this install keeps its state (HOUSEOS_STATE; a native install's default otherwise).
const STATE = process.env.HOUSEOS_STATE || "/opt/houseos/state";
const path = STATE + "/frontend/browser-test-session.json";
// The release the app announces (src/whats_new.ts), and preferences for someone who has seen
// every welcome: the welcomes would cover the pages in every test (onboarding.cjs shows them).
const RELEASE = fs
  .readFileSync(__dirname + "/../src/whats_new.ts", "utf8")
  .match(/export const RELEASE = "([\d.]+)"/)[1];
const settled = (role) => ({ onboarded: role, seen_release: RELEASE, tour_seen: true });
async function welcomeSeen(context, base, response) {
  try {
    const { csrf_token } = await response.json();
    await context.request.patch(base + "/api/v1/account/profile", {
      headers: { Origin: base, "X-CSRF-Token": csrf_token },
      data: { welcome_dismissed: true },
    });
    await context.request.put(base + "/api/v1/preferences", {
      headers: { Origin: base, "X-CSRF-Token": csrf_token },
      data: settled("admin"),
    });
  } catch {}
  return response;
}
module.exports = async function signIn(context, base) {
  if (base !== "http://127.0.0.1:8893")
    throw new Error("Browser fixtures only run against the isolated loopback test application");
  try {
    const saved = JSON.parse(fs.readFileSync(path, "utf8"));
    await context.addCookies(saved.cookies);
    const me = await context.request.get(base + "/api/v1/auth/me");
    if (me.ok()) return welcomeSeen(context, base, me);
  } catch {}
  const status = await (await context.request.get(base + "/api/v1/auth/status")).json();
  let data = { username: "visualtest", password: "Test-only-HouseOS-2046" };
  if (status.setup_required) {
    const line = fs
      .readFileSync(STATE + "/test.env", "utf8")
      .split("\n")
      .find((x) => x.startsWith("HOUSEOS_BOOTSTRAP_TOKEN="));
    data = {
      ...data,
      name: "Visual test resident",
      setup_token: line.slice(line.indexOf("=") + 1).replace(/^['"]|['"]$/g, ""),
    };
  }
  const response = await context.request.post(
    base + "/api/v1/auth/" + (status.setup_required ? "bootstrap" : "login"),
    { headers: { Origin: base }, data },
  );
  if (!response.ok()) throw new Error("Test authentication failed with HTTP " + response.status());
  fs.writeFileSync(path, JSON.stringify(await context.storageState()), {
    mode: 0o600,
  });
  fs.chmodSync(path, 0o600);
  return welcomeSeen(context, base, response);
};
// Waits for a Node-side condition (a captured request, say): true when it holds, false after
// `ms`, so the test's own assertion reports what is missing.
module.exports.RELEASE = RELEASE;
module.exports.settled = settled;
module.exports.until = async (fn, ms = 3000) => {
  for (const end = Date.now() + ms; !(await fn()); await new Promise((r) => setTimeout(r, 50)))
    if (Date.now() > end) return false;
  return true;
};
