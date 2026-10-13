import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// NFR07: automated WCAG 2.2 AA scan of every main screen, in both themes. Serious/critical violations fail.
const SCREENS = ["", "/write", "/bible", "/timeline", "/graph", "/continuity", "/sources", "/agents", "/proposals", "/insight", "/publish", "/settings"];

test("NFR07 — no serious or critical axe violations (dark & light)", async ({ page }) => {
  test.setTimeout(180_000);
  const email = `a11y-${Date.now()}@example.test`;
  await page.goto("/");
  await expect(page.locator("form")).toBeVisible();
  const loginScan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  const report: string[] = loginScan.violations.filter((v) => ["serious", "critical"].includes(v.impact || ""))
    .map((v) => `login: ${v.id} (${v.nodes.length}) ${v.help}`);
  await page.getByRole("button", { name: "ليس لديك حساب؟ أنشئ حساباً" }).click();
  await page.getByLabel("البريد الإلكتروني").fill(email);
  await page.getByLabel("كلمة المرور").fill("correct-horse-battery");
  await page.getByRole("button", { name: "إنشاء حساب" }).click();
  await page.getByRole("button", { name: "مشروع جديد" }).click();
  await page.getByLabel("عنوان الرواية").fill("فحص الوصول");
  await page.getByRole("button", { name: "إنشاء", exact: true }).click();
  await expect(page.getByRole("heading", { name: "سكرتارية التحرير" })).toBeVisible();
  const base = page.url();
  for (const theme of ["dark", "light"]) {
    await page.evaluate((t) => { document.documentElement.dataset.theme = t; localStorage.setItem("nis.theme", t); }, theme);
    for (const s of SCREENS) {
      await page.goto(base + s);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(300);
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      for (const v of r.violations.filter((x) => ["serious", "critical"].includes(x.impact || ""))) {
        report.push(`${theme} ${s || "/"}: ${v.id} (${v.nodes.length}) ${v.help} → ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`);
      }
    }
  }
  console.log(report.join("\n") || "no serious/critical violations");
  expect(report).toEqual([]);
});
