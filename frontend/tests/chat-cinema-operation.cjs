const { chromium } = require("/usr/lib/node_modules/playwright"),
  assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch(),
    context = await browser.newContext({ viewport: { width: 390, height: 844 } }),
    base = "http://127.0.0.1:8893";
  await require("./session.cjs")(context, base);
  const page = await context.newPage();
  let polls = 0,
    reads = 0;
  await page.route("**/api/v1/assistant/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    let data = {};
    if (p.endsWith("/status")) data = { actor_id: "fixture", available: true };
    else if (p.endsWith("/conversations"))
      data = { items: [{ id: "operation-test", title: "Movie request" }] };
    else {
      reads++;
      data = {
        messages: [
          {
            id: "answer",
            role: "assistant",
            content: "I’m finding versions of your movie.",
            cards: [
              {
                domain: "cinema",
                kind: "result",
                label: "Finding movie sources",
                status: polls > 1 ? "completed" : "accepted",
                operation_id: "fixture-operation",
                ...(polls > 1
                  ? {
                      workflow_id: "fixture-workflow",
                      items: [{ title: "A movie release", detail: "Unverified" }],
                    }
                  : {}),
              },
            ],
          },
        ],
      };
    }
    await route.fulfill({ json: data });
  });
  await page.route("**/api/v1/cinema/operations/fixture-operation", async (route) => {
    assert.equal(route.request().method(), "GET");
    polls++;
    await route.fulfill({
      json:
        polls === 1
          ? { status: "running" }
          : {
              status: "completed",
              workflow_id: "fixture-workflow",
              workflow: { id: "fixture-workflow" },
            },
    });
  });
  await page.goto(base + "/assistant?conversation=operation-test");
  const card = page.locator(".ask-card");
  await card.getByText("Finding movie sources…", { exact: true }).waitFor();
  await card.getByText("Versions found. Open Watch to play one.", { exact: true }).waitFor();
  await card.getByText("A movie release", { exact: true }).waitFor();
  assert.equal(
    await card.getByRole("link", { name: "Open Watch", exact: true }).getAttribute("href"),
    "/watch?workflow=fixture-workflow",
  );
  assert(reads >= 2);
  const completedPolls = polls;
  await page.waitForTimeout(2200);
  assert.equal(polls, completedPolls);
  await browser.close();
  console.log(
    "PASS bounded discovery progress, terminal message refresh, exact workflow link and polling stops",
  );
})().catch((e) => {
  console.error(String(e.message).split("Call log:")[0]);
  process.exit(1);
});
