// Nox's theme studio (Me → Theme studio): the setup guide without a model; openings; a picture
// added to a message (really uploaded, downscaled at home); a theme preview card that tries the
// theme on and back without a reload, keeps it, and starts a refinement. The model is mocked.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [],
    sent = [],
    kept = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let available = false,
    replied = false;
  const directions = {
    kind: "theme_directions",
    domain: "themes",
    status: "proposed",
    directions: [
      {
        name: "Azulejo",
        mood: "Blue on white glaze, a Lisbon kitchen at 8 a.m.",
        swatches: [
          { hex: "#f4f1ea", word: "glaze ground" },
          { hex: "#1f4e8c", word: "cobalt accent" },
          { hex: "#2b2b2b", word: "ink" },
        ],
        display_font: "Fraunces",
        body_font: "Source Sans 3",
        material: "glazed tile",
        why: "Your picture's cobalt and white.",
      },
    ],
  };
  const card = {
    kind: "theme_preview",
    domain: "themes",
    id: "base",
    status: "bundled",
    label: "Base",
    names: { en: "Base", fr: "Base" },
    description: { en: "Quiet and neutral.", fr: "Calme et neutre." },
    schemes: ["dark", "light"],
    scheme: "light",
    swatches: { light: ["#ffffff", "#eeeeee", "#111111", "#3b82f6", "#aaaaaa"] },
    mine: false,
  };
  await page.route("**/api/v1/assistant/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.includes("/attachments")) return route.continue(); // the real upload
    if (path.endsWith("/status"))
      return route.fulfill({ json: { actor_id: "fixture", available, purpose: "themes" } });
    if (path.endsWith("/conversations") && request.method() === "POST")
      return route.fulfill({ json: { id: "studio-thread" } });
    if (path.endsWith("/conversations")) return route.fulfill({ json: { items: [] } });
    if (path.endsWith("/chat")) {
      sent.push(request.postDataJSON());
      replied = true;
      return route.fulfill({ json: { status: "accepted", conversation_id: "studio-thread" } });
    }
    return route.fulfill({
      json: {
        pending: false,
        messages: replied
          ? [
              { id: "u", role: "user", content: sent[0]?.message, cards: [{ kind: "image", id: sent[0]?.attachments?.[0] }] },
              { id: "a", role: "assistant", content: "Here is a first direction.", cards: [directions, card] },
            ]
          : [],
      },
    }); // prettier-ignore
  });
  await page.route("**/api/v1/preferences", async (route) => {
    if (route.request().method() === "PUT") {
      kept.push(route.request().postDataJSON());
      return route.fulfill({ json: {} });
    }
    return route.continue();
  });

  // Making themes is the admins': Control Room → Themes → Make one with Nox.
  const openStudio = async () => {
    await page.goto(base + "/control?tab=themes");
    await page.getByRole("button", { name: "Make one with Nox" }).click();
  };
  // No model yet: the guide says where to set it up (the test user is an administrator).
  await openStudio();
  await page.getByText("The theme studio needs its own AI").waitFor();
  await page.getByRole("button", { name: "Set it up" }).waitFor();

  available = true;
  await openStudio();
  await page.getByText("Surprise me").waitFor();
  await page.getByText("From a place or an era").waitFor();
  // A picture goes to the house first (downscaled there), then with the message.
  const drawn = await page.evaluate(() => {
    const canvas = Object.assign(document.createElement("canvas"), { width: 400, height: 300 });
    const pen = canvas.getContext("2d");
    pen.fillStyle = "#c8642d";
    pen.fillRect(0, 0, 400, 300);
    pen.fillStyle = "#2d6a6a";
    pen.fillRect(0, 200, 400, 100);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.locator('input[type="file"][aria-label="Add a picture"]').setInputFiles({
    name: "kitchen.png",
    mimeType: "image/png",
    buffer: Buffer.from(drawn, "base64"),
  });
  await page.locator(".ask-pictures img").waitFor();
  await page.getByLabel("Message your assistant").fill("Like my kitchen");
  await page.getByRole("button", { name: "Send message" }).click();
  await page.getByText("Here is a first direction.").waitFor();
  assert.equal(sent[0].purpose, "themes");
  assert.equal(sent[0].attachments.length, 1);
  assert.equal(await page.locator(".ask-pictures").count(), 0, "sent pictures leave the composer");
  await page.locator("img.ask-picture").waitFor();

  // The directions are swatches with words, and one tap puts "build it" in the composer.
  await page.getByText("cobalt accent").waitFor();
  await page.getByRole("button", { name: "Build this one" }).click();
  assert.equal(
    await page.getByLabel("Message your assistant").inputValue(),
    "Let's build Azulejo.",
  );

  // The card: try it on (no reload), back, keep, refine.
  const before = await page.evaluate(() => document.documentElement.dataset.theme);
  let loads = 0;
  page.on("load", () => loads++);
  await page.getByRole("button", { name: "Try it on me" }).click();
  await page.waitForFunction(() => document.documentElement.dataset.theme === "base");
  await page.getByRole("button", { name: "Back to mine" }).click();
  await page.waitForFunction((id) => document.documentElement.dataset.theme === id, before);
  await page.getByRole("button", { name: "Keep it" }).click();
  await page.getByText("You're wearing Base.").waitFor();
  assert.deepEqual(kept.at(-1), { theme: "base" });
  await page.getByRole("button", { name: "Refine" }).click();
  assert.equal(await page.getByLabel("Message your assistant").inputValue(), "Change Base: ");
  assert.equal(loads, 0, "trying a theme never reloads");
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/theme-studio.png", fullPage: true });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("theme studio: guide, openings, picture upload, preview card try/back/keep/refine");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
