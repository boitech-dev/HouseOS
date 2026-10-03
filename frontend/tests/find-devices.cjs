// Control Room → Devices → Find devices: every kind found gets a way forward (Add, or a line on
// how to control it), and Add really enrolls the device (the scan result is mocked; the enrolment
// goes to the test house and is removed afterwards).
const { chromium } = require("/usr/lib/node_modules/playwright");
const assert = require("node:assert/strict");
const shots = process.env.HOUSEOS_SHOTS || "";
(async () => {
  const base = "http://127.0.0.1:8893";
  const browser = await chromium.launch({ headless: true });
  const devices = [
    {
      kind: "screen",
      name: "OLED TV",
      address: "192.0.2.50",
      maker: "LG Electronics",
      model: "OLED65C5",
      playable: false,
      brand: "lg",
    },
    {
      kind: "group",
      name: "Whole house",
      address: "192.0.2.61",
      port: 32187,
      maker: "Google Inc.",
      model: "Google Cast Group",
      playable: true,
      brand: "google",
    },
    {
      kind: "dlna",
      name: "Salon",
      address: "192.0.2.40",
      maker: "Sonos, Inc.",
      model: "Sonos One",
      playable: true,
      brand: "sonos",
      description_url: "http://192.0.2.40:1400/xml/device_description.xml",
    },
  ];
  for (const [width, height] of [
    [390, 844],
    [1280, 900],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } });
    await require("./session.cjs")(context, base);
    const page = await context.newPage();
    await page.route("**/api/v1/admin/devices/discover", (route) =>
      route.fulfill({
        json: {
          devices,
          scanned_at: "2026-09-25T21:00:00Z",
          scanning: false,
          scanner_running: true,
        },
      }),
    );
    await page.goto(base + "/control?tab=devices");
    const lg = page.locator(".ds-row", { hasText: "OLED TV" });
    await lg.waitFor();
    assert.match(await lg.locator(".ds-row__more").innerText(), /LG webOS TV/);
    assert.equal(await lg.getByRole("button", { name: "Add" }).count(), 0);
    const sonos = page.locator(".ds-row", { hasText: "Salon" }).first();
    assert.match(await sonos.locator(".ds-row__more").innerText(), /Sonos/);
    if (width === 390) {
      const created = page.waitForResponse(
        (r) => r.url().endsWith("/api/v1/cinema/devices") && r.request().method() === "POST",
      );
      await page
        .locator(".ds-row", { hasText: "Whole house" })
        .getByRole("button", { name: "Add" })
        .click();
      const response = await created;
      assert.equal(
        response.status(),
        200,
        "Add is accepted: " + (await response.text()) + " " + response.request().postData(),
      );
      const body = await response.json();
      assert.deepEqual([body.capabilities.kind, body.capabilities.port], ["group", 32187]);
      await page.locator(".ds-row", { hasText: "Whole house" }).getByText("Added").waitFor();
      const csrf = (await (await context.request.get(base + "/api/v1/auth/me")).json()).csrf_token;
      await context.request.delete(base + "/api/v1/cinema/devices/" + body.id, {
        headers: { Origin: base, "X-CSRF-Token": csrf },
      });
    }
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    if (shots)
      await page
        .locator(".ds-list", { has: page.locator(".ds-row", { hasText: "OLED TV" }) })
        .first()
        .screenshot({ path: `${shots}/find-devices-${width}.png` });
    await context.close();
  }
  await browser.close();
  console.log("find-devices: PASS");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
