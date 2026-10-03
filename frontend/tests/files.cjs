const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext();
  const base = "http://127.0.0.1:8893";
  const filename = "browser-upload-" + Date.now() + ".txt";
  const login = await require("./session.cjs")(c, base);
  assert(login.ok());
  const p = await c.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  p.on("response", async (r) => {
    if (r.status() >= 400)
      console.log(r.url().split("?")[0], r.status(), (await r.text()).slice(0, 500));
  });
  await p.goto(base + "/files", { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => document.querySelector("input[type=file]")?.disabled === false);
  await p.locator("input[type=file]").setInputFiles({
    name: filename,
    mimeType: "text/plain",
    buffer: Buffer.from("HouseOS browser upload test.\n"),
  });
  await p
    .getByText("stored", { exact: true })
    .waitFor({ timeout: 10000 })
    .catch(async (e) => {
      console.log(await p.getByRole("alert").allTextContents());
      throw e;
    });
  // The test house keeps every earlier run's uploads: find this one by its name.
  const find = () => p.getByPlaceholder("Search filenames…").fill(filename);
  await find();
  await p
    .getByRole("button", { name: "File actions · " + filename, exact: true })
    .first()
    .click();
  await p.getByRole("button", { name: "Move to trash", exact: true }).click();
  await p.getByRole("button", { name: "Confirm this change", exact: true }).click();
  await p.getByRole("button", { name: "Trash", exact: true }).click();
  await find();
  await p
    .getByRole("button", { name: "File actions · " + filename, exact: true })
    .first()
    .click();
  await p.getByRole("button", { name: "Restore", exact: true }).click();
  await p.getByRole("button", { name: "Confirm this change", exact: true }).click();
  await p.getByRole("button", { name: "My files", exact: true }).click();
  await find();
  await p
    .getByRole("button", { name: "File actions · " + filename, exact: true })
    .first()
    .waitFor();
  assert.equal(errors.length, 0, errors.join(";"));
  console.log("PASS real tus upload finalize, trash confirmation, restore confirmation");
  await b.close();
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
