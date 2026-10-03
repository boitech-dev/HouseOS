// Ask + voice: tap to talk (fake microphone); stopped by a tap, unsure words land in the
// composer to check (only a 2 s pause after speaking sends by itself), and Escape throws a
// recording away. Nox shows each state.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
  });
  const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      permissions: ["microphone"],
    }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    errors = [],
    voice = [],
    chats = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/v1/assistant/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    if (path.endsWith("/voice")) {
      voice.push({
        type: request.headers()["content-type"],
        size: request.postDataBuffer().length,
      });
      await new Promise((r) => setTimeout(r, 300));
      return route.fulfill({
        json: { text: "Ajoute du lait aux courses", language: "fr", duration: 2 },
      });
    }
    if (path.endsWith("/chat")) chats.push(request.postDataJSON());
    if (path.endsWith("/status"))
      return route.fulfill({ json: { actor_id: "fixture", available: true, purpose: "general" } });
    return route.fulfill({ json: { items: [], next_offset: null } });
  });
  await page.goto(base + "/house");
  await page.locator(".shell__main").waitFor();
  await page.locator(".shell__door--ask:visible").click();
  const ask = page.getByRole("dialog", { name: "Nox" });
  await ask.getByText("Nox is here.").waitFor();
  const mic = ask.getByRole("button", { name: "Talk to Nox" });
  await mic.click();
  await ask.getByText("Listening… pause to send, tap to stop").waitFor();
  await ask.getByText("Nox is listening…").waitFor();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: "evidence/latest/ask-listening-phone.png" });
  await ask.getByRole("button", { name: "Stop and use what I said" }).click();
  await ask.getByText("Nox is thinking…").waitFor();
  const composer = ask.locator("textarea");
  await page.waitForFunction(
    () => document.querySelector("dialog textarea")?.value === "Ajoute du lait aux courses",
  );
  assert.equal(voice.length, 1);
  assert(
    /^audio\/(webm|mp4|ogg)/.test(voice[0].type) && voice[0].size > 500,
    JSON.stringify(voice),
  );
  assert.equal(chats.length, 0, "a transcript is never sent without the resident");
  assert.equal(await composer.inputValue(), "Ajoute du lait aux courses");

  // Escape throws the recording away.
  await mic.click();
  await ask.getByText("Listening… pause to send, tap to stop").waitFor();
  await page.waitForTimeout(600);
  await ask.getByRole("button", { name: "Stop and use what I said" }).press("Escape");
  await page.waitForTimeout(800);
  assert.equal(voice.length, 1, "cancelled recording was not uploaded");
  assert.equal(await composer.inputValue(), "Ajoute du lait aux courses");
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS voice to composer (no auto-send), Escape discards, Nox states");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
