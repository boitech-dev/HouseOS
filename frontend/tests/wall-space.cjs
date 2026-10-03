const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true }),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  let rows = Array.from({ length: 30 }, (_, i) => ({
    id: String(i),
    author_name: i % 2 ? "Mira" : "Jules",
    created_at: "2026-09-22T16:00:00Z",
    data: { body: "Message " + i, title: "" },
  }));
  let sent = 0;
  await page.route("**/api/v1/household/board?*", (r) => {
    const u = new URL(r.request().url()),
      offset = Number(u.searchParams.get("offset")),
      limit = Number(u.searchParams.get("limit"));
    return r.fulfill({
      json: { items: rows.slice(offset, offset + limit), has_more: rows.length > offset + limit },
    });
  });
  await page.route("**/api/v1/household/board", (r) => {
    const d = r.request().postDataJSON();
    assert.deepEqual(d.data, { body: "Dinner at eight 🍲", color: "", pinned: false, importance: "normal" });
    sent++;
    rows.unshift({
      id: "new",
      author_name: "Mira",
      created_at: "2026-09-22T17:00:00Z",
      data: d.data,
    });
    return r.fulfill({ status: 201, json: rows[0] });
  });
  await page.goto(base + "/house");
  await page.locator(".house-note").first().waitFor();
  assert.equal(await page.locator(".house-note").count(), 24);
  await page.locator(".house-wall .house-pages button").last().click();
  await page.getByText("Message 29", { exact: true }).waitFor();
  assert.equal(await page.locator(".house-note").count(), 6);
  await page.locator(".house-wall__compose textarea").fill("Dinner at eight 🍲");
  await page.locator(".house-wall__compose button[type=submit]").click();
  await page.locator(".house-note").getByText("Dinner at eight 🍲", { exact: true }).waitFor();
  await page.waitForFunction(
    () => document.querySelector(".house-wall__compose textarea").value === "",
  );
  assert.equal(await page.locator(".house-wall__compose textarea").inputValue(), "");
  assert.equal(sent, 1);
  assert.equal(await page.getByRole("dialog").count(), 0);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/wall-inline-phone.png", fullPage: true });
  await page.route("**/api/v1/personal-space/**", (r) => {
    const path = new URL(r.request().url()).pathname;
    return r.fulfill({
      json: path.endsWith("/config")
        ? { configured: true, setup_complete: true, version: 1 }
        : {
            selected_at: "2026-09-22T12:00:00Z",
            sections: [
              {
                kind: "news",
                items: [{ id: "n", title: "News fixture", url: "https://example.org" }],
              },
              {
                kind: "art",
                items: [
                  {
                    id: "a",
                    title: "Illustration fixture",
                    artist: "Test artist",
                    url: "https://example.org",
                    poster: base + "/test-art.svg",
                  },
                ],
              },
            ],
          },
    });
  });
  await page.route("**/test-art.svg", (r) =>
    r.fulfill({
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600"><rect width="400" height="600" fill="#302444"/><circle cx="270" cy="160" r="70" fill="#d0bbaa"/><path d="M0 500L130 260L400 600H0" fill="#686070"/></svg>',
    }),
  );
  await page.goto(base + "/space");
  await page.locator(".space-gallery img").waitFor();
  const positions = await page.evaluate(() => ({
    art: document.querySelector(".space-gallery").getBoundingClientRect().top,
    news: [...document.querySelectorAll("a")]
      .find((x) => x.textContent.includes("News fixture"))
      .getBoundingClientRect().top,
    image: document.querySelector(".space-gallery img").getBoundingClientRect().height,
  }));
  assert(positions.art < positions.news);
  assert(positions.image >= 200); // a strip of whole pictures, not one giant each
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/myspace-art-first-phone.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: "evidence/latest/myspace-art-first-desktop.png", fullPage: true });
  await browser.close();
  console.log(
    "PASS: inline wall/send/older pages/no modal/author/mobile width; art first/larger/desktop and phone.",
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
