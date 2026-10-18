/* Optional browser check: npm install --no-save playwright && node tests/web_browser.cjs */
const assert = require("node:assert/strict");
const { chromium } = require(process.argv[2] || "playwright");
const base = process.env.SPLITFORGE_WEB_URL || "http://127.0.0.1:8765";

(async () => {
  if (process.env.SPLITFORGE_SCREENSHOTS)
    require("node:fs").mkdirSync(process.env.SPLITFORGE_SCREENSHOTS, {
      recursive: true,
    });
  let available = false;
  for (let attempt = 0; attempt < 50; attempt++) {
    try {
      if ((await fetch(base + "/api/session")).ok) {
        available = true;
        break;
      }
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(
    available,
    "Start the SplitForge web demo before running browser checks",
  );
  const browser = await chromium.launch({
    headless: true,
    ...(process.platform === "win32" ? { channel: "chrome" } : {}),
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1050 },
      reducedMotion: "reduce",
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (
        /Content Security Policy|Refused to (execute|apply)/.test(
          message.text(),
        )
      )
        errors.push(message.text());
    });
    await page.goto(base);
    await page.getByRole("button", { name: "Explore read-only demo" }).click();
    await page
      .getByRole("heading", { name: "Your apps. Your network." })
      .waitFor();
    assert.equal(await page.locator("#main-content tbody tr").count(), 7);
    if (process.env.SPLITFORGE_SCREENSHOTS)
      await page.screenshot({
        path: process.env.SPLITFORGE_SCREENSHOTS + "/web-overview.png",
        fullPage: true,
      });
    await page
      .getByRole("button", { name: "App router", exact: false })
      .first()
      .click();
    await page.locator("#search").fill("telegram");
    assert.equal(await page.locator("#main-content tbody tr").count(), 1);
    await page.locator(".route-pill").click();
    await page
      .getByRole("heading", { name: "Assign route · telegram_bot.py" })
      .waitFor();
    await page.locator("#route-profile").selectOption("");
    await page.getByRole("button", { name: "Apply & restart" }).click();
    await page
      .locator("#form-error")
      .filter({ hasText: "Read-only demo" })
      .waitFor();
    await page.getByRole("button", { name: "Close dialog" }).click();
    await page
      .getByRole("button", { name: "Register app", exact: false })
      .click();
    await page.locator("#field-name").fill("draft-app");
    await page.getByRole("button", { name: "Browse server files" }).click();
    await page
      .getByRole("button", { name: "telegram_bot.py", exact: false })
      .click();
    assert.equal(await page.locator("#field-name").inputValue(), "draft-app");
    assert.match(await page.locator("#field-command").inputValue(), /python3/);
    await page.getByRole("button", { name: "Register workload" }).click();
    await page
      .locator("#form-error")
      .filter({ hasText: "Read-only demo" })
      .waitFor();
    assert.equal(
      new URL(page.url()).search,
      "",
      "Forms must never submit secrets through URL query strings",
    );
    await page.getByRole("button", { name: "Close dialog" }).click();
    await page
      .getByRole("button", { name: "Tunnel profiles", exact: false })
      .click();
    assert.equal(await page.locator(".profile-card").count(), 3);
    await page
      .getByRole("button", { name: "Import profile", exact: false })
      .click();
    await page.locator("#profile-method").selectOption("slipstream");
    assert.equal(await page.locator("#profile-dns-fields").isVisible(), true);
    assert.equal(
      await page.locator("#profile-import-fields").isVisible(),
      false,
    );
    await page.getByRole("button", { name: "Close dialog" }).click();
    await page
      .getByRole("button", { name: "Core installer", exact: false })
      .click();
    await page.locator('input[value="dnstt-client"]').check();
    assert.match(await page.locator("#core-plan").textContent(), /xray/);
    assert.match(await page.locator("#core-plan").textContent(), /tun2socks/);
    await page.getByRole("button", { name: "Install selected cores" }).click();
    await page
      .locator("#toast")
      .filter({ hasText: "Read-only demo" })
      .waitFor();
    await page
      .getByRole("button", { name: "Security & DNS", exact: false })
      .click();
    await page.locator("#dns-profile").selectOption("ab000002");
    await page.locator("#dns-url").fill("https://dns.example.com/dns-query");
    await page.waitForTimeout(3500);
    assert.equal(
      await page.locator("#dns-url").inputValue(),
      "https://dns.example.com/dns-query",
      "Polling must not erase edits",
    );
    await page.getByRole("button", { name: "Live logs", exact: false }).click();
    await page
      .locator("#journal-output")
      .filter({ hasText: "Control plane ready" })
      .waitFor();
    await page
      .getByRole("button", { name: "Check health", exact: true })
      .click();
    await page
      .locator("#toast")
      .filter({ hasText: "Read-only demo" })
      .waitFor();
    await page
      .getByRole("button", { name: "Check & repair", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Check & repair now", exact: true })
      .click();
    await page
      .locator("#form-error")
      .filter({ hasText: "Read-only demo" })
      .waitFor();
    await page.getByRole("button", { name: "Close dialog" }).click();
    await page.route("**/api/state", async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      body.diagnostics = {
        errors: 1,
        warnings: 0,
        updated: Date.now() / 1000,
        checks: [
          {
            category: "dns",
            scope: "fixture",
            status: "error",
            message: "Fixture DNS check failed",
            remedy: "Inspect encrypted DNS settings",
            repaired: false,
          },
        ],
      };
      await route.fulfill({ response, json: body });
    });
    await page.locator("#refresh-button").click();
    await page.getByText("Fixture DNS check failed", { exact: false }).waitFor();
    await page.unroute("**/api/state");
    await page
      .getByRole("button", { name: "Quick start", exact: false })
      .click();
    await page.getByRole("button", { name: "فارسی", exact: true }).click();
    assert.equal(await page.locator(".help-steps").getAttribute("dir"), "rtl");
    await page.route("**/api/state", async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      body.profiles[0].name = '<img src=x onerror="window.injected=true">';
      await route.fulfill({ response, json: body });
    });
    await page.locator("#refresh-button").click();
    await page.waitForTimeout(400);
    await page.locator('[data-page="profiles"]').first().click();
    assert.equal(
      await page.locator("#main-content img").count(),
      0,
      "User labels must be escaped",
    );
    assert.equal(await page.evaluate(() => window.injected), undefined);
    await page.unroute("**/api/state");
    await page.goto(base + "/#overview");
    await page.reload();
    await page.locator("#main-content tbody tr").first().waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator("#menu-toggle").click();
    await page
      .getByRole("button", { name: "Overview", exact: false })
      .first()
      .click();
    assert.equal(await page.locator(".sidebar.open").count(), 0);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
      "No mobile page overflow",
    );
    if (process.env.SPLITFORGE_SCREENSHOTS)
      await page.screenshot({
        path: process.env.SPLITFORGE_SCREENSHOTS + "/web-mobile.png",
        fullPage: true,
      });
    await page.locator("#menu-toggle").click();
    await page.locator("#logout-button").click();
    await page.locator("#login-view").waitFor({ state: "visible" });
    assert.deepEqual(errors, [], `Browser errors: ${errors.join("; ")}`);
    console.log(
      "PASS: dashboard, routing, demo guard, profiles, prerequisites, polling, logs, Persian help, mobile navigation and logout.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
