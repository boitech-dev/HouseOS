const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
// Files → Films: a saved film opens with "Play here" and "Send to the TV" (it used to say
// "Not found": the sheet asked for /api/v1/api/v1/…). The API is mocked; nothing plays.
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  const errors = [],
    asked = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => r.url().includes("/browser") && asked.push(new URL(r.url()).pathname));
  await page.route(/\/api\/v1\/files\/library\?/, (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: "f1",
            title: "Saved Fixture Film",
            type: "film",
            year: 2008,
            version: 1,
            played_by: [],
            size: 1000,
            watch: "/watch?title=t1",
            browser: "/api/v1/files/library/films/f1/browser",
          },
        ],
        total: 1,
        facets: { genres: [], types: [], people: [] },
        next_offset: null,
      },
    }),
  );
  await page.route("**/api/v1/files/library/films/f1/browser", (route) =>
    route.fulfill({
      json: { playable: true, stream: "/api/v1/files/library/films/f1/stream", reason: null },
    }),
  );
  await page.goto(base + "/files");
  await page.getByRole("button", { name: "Films & series" }).click();
  await page.getByText("Saved Fixture Film").click();
  const sheet = page.getByRole("dialog", { name: "Saved Fixture Film" });
  await sheet.getByRole("button", { name: /Play here/ }).waitFor();
  await sheet.getByRole("button", { name: "Send to the TV" }).waitFor();
  assert.deepEqual(asked, ["/api/v1/files/library/films/f1/browser"]);
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS a saved film offers Play here and Send to the TV");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
