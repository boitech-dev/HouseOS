// Watch → Web: a shared message opens the Web tab with its link, Play sends it to the TV, the
// list shows progress, a clear failure, and "replace what's on" (D32). Real isolated login; the
// cinema web and device reads/writes are intercepted, so nothing downloads or plays.
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage(),
    errors = [],
    writes = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const tv = { id: "tv1", name: "Living-room TV", adapter: "cast", state: "idle" };
  const videos = [
    { id: "v1", url: "https://youtu.be/abcdefghijk", title: "A cat on a piano", site: "Youtube",
      duration: 125, state: "downloading", progress: 0.4, workflow_state: "playing_observed", device_id: "tv1" },
    { id: "v2", url: "https://www.twitch.tv/someone", title: "", site: "", state: "failed",
      error: "WEB_VIDEO_LIVE", device_id: "tv1" },
    { id: "v3", url: "https://www.reddit.com/r/x", title: "Small heart attack", site: "Reddit",
      duration: 12, state: "ready", kept: true, needs_replace: true, device_id: "tv1" },
  ]; // prettier-ignore
  await page.route(/\/api\/v1\/cinema\/(web|devices|preferences)(\/.*)?$/, async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname.slice("/api/v1/cinema".length);
    let data = { items: [] };
    if (request.method() !== "GET") {
      writes.push({ path, method: request.method(), body: request.postDataJSON() });
      data = { id: "v4", state: "queued" };
    } else if (path === "/devices") data = { items: [tv] };
    else if (path === "/preferences") data = { preferred_device: "tv1" };
    else if (path === "/web") data = { items: videos };
    await route.fulfill({ json: data });
  });
  // A phone's Share → HouseOS lands in Capture, which sends a link here.
  const shared = "Look at this! https://youtu.be/abcdefghijk?si=x";
  await page.goto(base + "/watch?kind=web&text=" + encodeURIComponent(shared));
  const field = page.getByRole("textbox", { name: "A video link" });
  assert.equal(await field.inputValue(), shared);
  await page.getByRole("button", { name: "Play on Living-room TV" }).click();
  await page.getByText("Getting it ready for Living-room TV…").waitFor();
  assert.deepEqual(writes[0], {
    path: "/web",
    method: "POST",
    body: { text: shared, device_id: "tv1" },
  });
  assert.equal(await field.inputValue(), "");
  // Progress, a failure in words, and a video waiting to replace what is on the TV.
  await page.getByRole("progressbar", { name: "Downloading…" }).waitFor();
  // It plays from its first pieces, and the card says when the house deletes it.
  await page
    .getByText("Playing while it downloads 40% · deleted from the house 6 h after you watch it")
    .waitFor();
  await page.getByText("Live streams can't play here yet.").waitFor();
  await page.getByText("Something else is on Living-room TV.").waitFor();
  await page.getByRole("button", { name: "Replace it" }).click();
  assert(
    writes.some(
      (w) => w.path === "/web/v3/play" && w.body.replace === true && w.body.device_id === "tv1",
    ),
  );
  await page.getByRole("button", { name: "Remove · www.twitch.tv" }).click();
  assert(writes.some((w) => w.path === "/web/v2" && w.method === "DELETE"));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: "evidence/latest/watch-web-phone.png", fullPage: true });
  assert.deepEqual(errors, []);
  await browser.close();
  console.log("PASS shared link, play on the TV, progress, failure words, replace, remove");
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
