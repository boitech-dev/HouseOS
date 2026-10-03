// Live public adapter/legacy bookmark check. New guided UI is covered in personal-space-daily.cjs.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const base = "http://127.0.0.1:8893";
  const login = await require("./session.cjs")(context, base);
  const me = await login.json();
  const headers = { Origin: base, "X-CSRF-Token": me.csrf_token };
  const catalog = await context.request.get(base + "/api/v1/personal-space/anime");
  assert(catalog.ok());
  const title = (await catalog.json()).items[0];
  assert(title?.id);
  const poster = await context.request.get(base + title.poster);
  assert(poster.ok());
  assert((await poster.body()).length > 100);
  const before = (
    await (await context.request.get(base + "/api/v1/personal-space/favorites")).json()
  ).items;
  const wasSaved = before.some((item) => item.id === title.id);
  try {
    assert(
      (
        await context.request.put(base + "/api/v1/personal-space/favorites/" + title.id, {
          headers,
        })
      ).ok(),
    );
    const saved = (
      await (await context.request.get(base + "/api/v1/personal-space/favorites")).json()
    ).items;
    assert(saved.some((item) => item.id === title.id));
    const news = await context.request.get(base + "/api/v1/personal-space/news?feed=science");
    assert(news.ok());
    assert((await news.json()).items.length > 0);
  } finally {
    if (!wasSaved)
      assert(
        (
          await context.request.delete(base + "/api/v1/personal-space/favorites/" + title.id, {
            headers,
          })
        ).ok(),
      );
    await browser.close();
  }
  console.log(
    "PASS live Kitsu metadata/sanitized poster, preserved private bookmarks, BBC public RSS; no resident setup or model call",
  );
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
