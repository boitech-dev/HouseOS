// Ctrl+K's numbered quick actions (a digit, the text, Enter) and Home's who's-home pop-up.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [], posts = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const me = await (await context.request.get(base + "/api/v1/auth/me")).json();
  const people = [
    { id: me.user.id, name: "Me", avatar: "crest", home: true },
    { id: "p-home", name: "Sam", avatar: "moon", home: true },
    { id: "p-away", name: "Jo", avatar: "bat", home: false },
  ];
  await page.route("**/api/v1/people", (r) => r.fulfill({ json: people }));
  await page.route("**/api/v1/household/groceries", (r) => {
    if (r.request().method() !== "POST") return r.continue();
    posts.push(r.request().postDataJSON());
    return r.fulfill({ json: { id: "g1", status: "completed" } });
  });
  await page.goto(base + "/house");
  await page.getByRole("heading", { name: "House", level: 1 }).waitFor();
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Go to, do or ask" });
  await palette.getByRole("option", { name: /Add a song/ }).waitFor();
  // 2: groceries, one per Enter; the box stays, cleared, for the next.
  await page.keyboard.press("2");
  await palette.getByRole("button", { name: /Add to the groceries/ }).waitFor();
  await page.keyboard.type("Oat milk");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector(".ds-palette input")?.value === "");
  assert.equal(posts[0].data.label, "Oat milk");
  // Backspace on an empty box: back to the quick actions; 3 lists the housemates (not me).
  await page.keyboard.press("Backspace");
  await page.keyboard.press("3");
  await palette.getByRole("option", { name: /Sam/ }).waitFor();
  assert.equal(await palette.getByRole("option", { name: /^Me/ }).count(), 0);
  await page.keyboard.press("Escape");
  // Searching ranks the name first; "Ask Nox" comes last.
  await page.keyboard.press("Control+k");
  await page.keyboard.type("secu");
  const first = palette.getByRole("option").first();
  assert.match(await first.innerText(), /Security/);
  await page.keyboard.press("Escape");
  // Home: only who's home, as faces; the pop-up lists everyone, with a message each.
  await page.goto(base + "/");
  const who = page.locator(".home-who .ds-popover__trigger");
  assert.match(await who.innerText(), /2 at home/);
  await who.click();
  const pop = page.getByRole("dialog", { name: "Who is around" });
  await pop.getByText("Jo").waitFor();
  await pop.getByRole("button", { name: "Message Sam" }).click();
  await page.waitForURL(base + "/inbox?with=new&to=p-home");
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("palette and presence ok");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
