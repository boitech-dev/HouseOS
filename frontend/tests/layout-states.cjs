// Synthetic read-only layout fixtures. These are not media/physical playback evidence.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const fs = require("fs");
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext({ viewport: { width: 1440, height: 900 } });
  await require("./session.cjs")(c, "http://127.0.0.1:8893");
  const p = await c.newPage();
  const queue = Array.from({ length: 100 }, (_, i) => ({
    id: "layout-" + i,
    title:
      i === 0
        ? "SYNTHETIC LONG TITLE — " + "A very long music title 🎵 ".repeat(16)
        : "Synthetic queued track " + (i + 1),
    source_url: "https://www.youtube.com/watch?v=testonly001",
    uploader: "Layout fixture only",
    duration: 300,
    status: "ready",
  }));
  await p.route("**/api/v1/music", (r) =>
    r.fulfill({
      json: {
        version: 1,
        current_id: null,
        desired: "paused",
        volume: 25,
        items: queue,
        observation: { status: "unavailable" },
        physical_verified: false,
      },
    }),
  );
  await p.route(/\/api\/v1\/household\/board(?:\?|$)/, (r) =>
    r.fulfill({
      json: {
        items: [
          {
            id: "synthetic-board",
            version: 1,
            created_at: "2026-09-20T10:00:00Z",
            data: {
              title: "Urgent note — synthetic layout fixture",
              body: "Readable urgent note. " + "LongUnbrokenText".repeat(15),
              importance: "urgent",
              pinned: true,
            },
          },
        ],
      },
    }),
  );
  await p.goto("http://127.0.0.1:8893/music", {
    waitUntil: "domcontentloaded",
  });
  // /music redirects to /listen: a long queue draws 30 songs, then 30 more as its end comes near.
  await p.waitForFunction(() => document.querySelectorAll(".listen-queue .ds-row").length === 30);
  for (const n of [60, 90, 100]) {
    await p.locator(".listen-queue .ds-more").scrollIntoViewIfNeeded();
    await p.waitForFunction((n) => document.querySelectorAll(".listen-queue .ds-row").length === n, n);
  }
  await p.screenshot({
    path: "evidence/latest/music-100-synthetic-desktop.png",
    fullPage: false,
  });
  await p.setViewportSize({ width: 360, height: 800 });
  assert(
    await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    "long100queue overflows360",
  );
  await p.screenshot({
    path: "evidence/latest/music-long-synthetic-phone.png",
    fullPage: false,
  });
  // The wall lives in House (Home counts it on the House tile).
  await p.goto("http://127.0.0.1:8893/house", { waitUntil: "domcontentloaded" });
  await p.getByText("Urgent note — synthetic layout fixture", { exact: true }).waitFor();
  assert(
    await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    "urgent longnote overflows",
  );
  await p.screenshot({
    path: "evidence/latest/house-urgent-synthetic-phone.png",
    fullPage: true,
  });
  await p.route("**/api/v1/files/uploads", (r) =>
    r.fulfill({
      status: 503,
      json: { detail: "Synthetic storage unavailable. Nothing stored." },
    }),
  );
  await p.goto("http://127.0.0.1:8893/files", {
    waitUntil: "domcontentloaded",
  });
  await p.waitForFunction(() => document.querySelector("input[type=file]")?.disabled === false);
  await p.locator("input[type=file]").setInputFiles({
    name: "synthetic-failure.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("failure fixture"),
  });
  await p.getByRole("alert").filter({ hasText: "Synthetic storage unavailable" }).waitFor();
  assert.equal(await p.getByText("stored", { exact: true }).count(), 0);
  fs.writeFileSync(
    "evidence/latest/layout-states-result.json",
    JSON.stringify(
      {
        passed: true,
        evidence:
          "Read-only intercepted synthetic layout and failure fixtures; no physical media claim",
        checks: [
          "100-itemqueue",
          "longtitle360px",
          "urgentunbrokentext360px",
          "uploadfailuredoesnotreportstored",
        ],
      },
      null,
      2,
    ),
  );
  await b.close();
  console.log("PASS synthetic100queue/longtitle/urgentnote/uploadfailure layouts");
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
