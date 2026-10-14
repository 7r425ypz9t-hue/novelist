import { expect, Page, test } from "@playwright/test";

const password = "correct-horse-battery";

async function register(page: Page, name: string) {
  const email = `${name}-${Date.now()}@example.test`;
  await page.goto("/");
  await page.getByRole("button", { name: "ليس لديك حساب؟ أنشئ حساباً" }).click();
  await page.getByLabel("الاسم الظاهر").fill(name);
  await page.getByLabel("البريد الإلكتروني").fill(email);
  await page.getByLabel("كلمة المرور").fill(password);
  await page.getByRole("button", { name: "إنشاء حساب" }).click();
  await expect(page.getByRole("heading", { name: "مشاريعك الروائية" })).toBeVisible();
  return email;
}

async function newNovelWithScene(page: Page, title: string) {
  await page.getByRole("button", { name: "مشروع جديد" }).click();
  await page.getByLabel("عنوان الرواية").fill(title);
  await page.getByRole("button", { name: "إنشاء", exact: true }).click();
  await expect(page.getByRole("heading", { name: "سكرتارية التحرير" })).toBeVisible();
  await expect(page.getByText("كلما اتسعت الرؤية ضاقت العبارة")).toBeVisible();
  await page.getByRole("link", { name: "غرفة الكتابة" }).click();
  await page.getByRole("button", { name: "+ فصل" }).click();
  await page.getByRole("button", { name: "+ مشهد" }).click();
  // wait for the NEW scene to be the open unit, then for it to be editable (it is locked while switching)
  await expect(page.getByText("الفصل 1 · المشهد 1").first()).toBeVisible();
  await expect(page.locator('.ProseMirror[contenteditable="true"]')).toBeVisible();
}

const saveState = (page: Page) => page.getByTestId("save-state");

test("AT01/AT02 — create, write mixed RTL/LTR text, autosave, persists after re-login", async ({ page, context }) => {
  const email = await register(page, "author");
  await expect(page).toHaveTitle("كاتب");
  await expect(page.locator(".brand")).toContainText("كاتب");
  await expect(page.locator("body")).not.toContainText("ذكاء الرواية");
  await newNovelWithScene(page, "رواية الشاطئ");
  await expect(page).toHaveTitle("رواية الشاطئ — كاتب");
  const editor = page.locator(".ProseMirror");
  await editor.click();
  await page.keyboard.type("قال نادر: «سأصل في 10:30 مع John إلى Port-Said» ثم مضى، أليس كذلك؟");
  await expect(saveState(page)).toHaveText(/محفوظ على الخادم/, { timeout: 15_000 });
  await expect(page.getByTestId("live-words")).toHaveText(/15 كلمة/) // 10:30 and Port-Said are two tokens each, same rule as the server;
  // Arabic paragraph is rendered right-to-left even though it contains Latin runs and digits
  const dir = await editor.locator("p").first().evaluate((el) => getComputedStyle(el).direction);
  expect(dir).toBe("rtl");
  // owner typography (D-18): manuscript text 14px, line spacing 1.5; tagline «استديو الرواية»
  const type = await editor.evaluate((el) => { const c = getComputedStyle(el); return [c.fontSize, c.lineHeight, c.fontFamily.split(",")[0].replace(/"/g, "")]; });
  expect(type).toEqual(["14px", "21px", "Amiri"]); // D-20: Amiri (OFL) is the manuscript face
  expect(await page.evaluate(() => document.fonts.check('14px "Amiri"', "كاتب"))).toBe(true);
  await expect(page.locator(".brand")).toContainText("استديو الرواية");
  const url = page.url();
  // new session
  await context.clearCookies();
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.goto("/");
  await page.getByLabel("البريد الإلكتروني").fill(email);
  await page.getByLabel("كلمة المرور").fill(password);
  await page.getByRole("button", { name: "دخول" }).click();
  await expect(page.getByText("رواية الشاطئ")).toBeVisible();
  await page.goto(url);
  await expect(page.locator(".ProseMirror")).toContainText("سأصل في 10:30 مع John إلى Port-Said");
});

test("AT03 — network loss keeps edits locally and syncs on reconnect; crash recovery from journal", async ({ page, context }) => {
  const email = await register(page, "offline");
  await newNovelWithScene(page, "رواية الانقطاع");
  const editor = page.locator(".ProseMirror");
  await editor.click();
  await page.keyboard.type("سطر أول قبل الانقطاع.");
  await expect(saveState(page)).toHaveText(/محفوظ على الخادم/, { timeout: 15_000 });

  await context.setOffline(true);
  await page.keyboard.type(" سطر كُتب دون شبكة.");
  await expect(saveState(page)).toHaveText(/غير متصل|محفوظ محلياً/, { timeout: 15_000 });
  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(saveState(page)).toHaveText(/محفوظ على الخادم/, { timeout: 20_000 });

  // crash: type and close the tab before the server sync fires; the IndexedDB journal must restore it
  const url = page.url();
  await page.keyboard.type(" جملة لم تُزامن بعد.");
  await page.waitForTimeout(900); // > local journal debounce (600 ms), < server sync delay
  const journaled = await page.evaluate(() => new Promise<number>((res) => {
    const r = indexedDB.open("nis-journal");
    r.onsuccess = () => { const c = r.result.transaction("pending").objectStore("pending").count(); c.onsuccess = () => res(c.result); };
  }));
  expect(journaled).toBe(1); // the unsynced edit is safe in the local journal before the "crash"
  await page.close({ runBeforeUnload: false });
  const again = await context.newPage(); // a fresh tab: the session token (sessionStorage) is gone, the journal is not
  await again.goto("/");
  await again.getByLabel("البريد الإلكتروني").fill(email);
  await again.getByLabel("كلمة المرور").fill(password);
  await again.getByRole("button", { name: "دخول" }).click();
  await expect(again.getByRole("heading", { name: "مشاريعك الروائية" })).toBeVisible();
  await again.goto(url);
  await expect(again.locator(".ProseMirror")).toContainText("جملة لم تُزامن بعد", { timeout: 15_000 });
  await expect(again.getByTestId("save-state")).toHaveText(/محفوظ على الخادم/, { timeout: 20_000 });
});

test("AT06 — an agent's deletion proposal changes nothing until the author accepts it", async ({ page }) => {
  await register(page, "editor");
  await newNovelWithScene(page, "رواية المقترحات");
  const editor = page.locator(".ProseMirror");
  await editor.click();
  const para = "كان الموج يضرب الصخور في المساء الطويل بلا توقف.";
  await page.keyboard.type(para);
  await page.keyboard.press("Enter");
  await page.keyboard.type(para);
  await expect(saveState(page)).toHaveText(/محفوظ على الخادم/, { timeout: 15_000 });
  const writeUrl = page.url();

  await page.getByRole("link", { name: "غرفة الوكلاء" }).click();
  await page.locator(".card", { hasText: "المحرر الأدبي" }).getByRole("button", { name: "تشغيل" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "تشغيل" }).click();
  await expect(page.getByRole("dialog").getByText("اكتمل").first()).toBeVisible({ timeout: 20_000 });

  await page.goto(writeUrl);
  await expect(page.locator(".ProseMirror p")).toHaveCount(2); // untouched

  await page.getByRole("link", { name: "المقترحات والنقد" }).click();
  await page.getByText("حذف فقرة مكررة حرفياً").first().click();
  await page.getByRole("button", { name: "قبول", exact: true }).click();
  await expect(page.getByText("قُبل المقترح وأُنشئت مراجعة جديدة")).toBeVisible();

  await page.goto(writeUrl);
  await expect(page.locator(".ProseMirror p")).toHaveCount(1);
  await page.getByRole("tab", { name: "المراجعات" }).click();
  await expect(page.getByText("مقترح مقبول")).toBeVisible();
});

test("R4 — story time can be entered in the Hijri calendar", async ({ page }) => {
  await register(page, "hijri");
  await newNovelWithScene(page, "رواية التقويم");
  await page.getByLabel("السنة في التقويم").fill("1377");
  await page.getByLabel("الشهر في التقويم").selectOption({ label: "رمضان" });
  await page.getByLabel("اليوم في التقويم").fill("1");
  await page.getByRole("button", { name: "تحويل" }).click();
  await expect(page.getByLabel("وصف الزمن")).toHaveValue("1 رمضان 1377 هـ");
  const t = Number(await page.getByLabel("زمن القصة (سنة)").inputValue());
  expect(t).toBeGreaterThan(1958.2);
  expect(t).toBeLessThan(1958.4); // ≈ 21 March 1958
  await page.getByRole("button", { name: "حفظ المصفوفة" }).click();
  await expect(page.getByText("حُفظت مصفوفة المشهد")).toBeVisible();
});

test("FR04 — Arabic-aware find: tashkeel, hamza and taa forms match; whole-manuscript hits jump to the unit", async ({ page }) => {
  await register(page, "finder");
  await newNovelWithScene(page, "رواية البحث");
  await page.locator(".ProseMirror").click();
  await page.keyboard.insertText("قالت إنّ الحياةَ قصيرةٌ، وإنتهى الكلام.");
  await expect(saveState(page)).toHaveText(/محفوظ على الخادم/, { timeout: 15_000 });
  await page.keyboard.press("Control+f");
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("ابحث عن").fill("ان الحياة قصيره");
  await expect(dialog.getByText("1 من 1")).toBeVisible();
  await dialog.getByLabel("كلمة كاملة").check();
  await dialog.getByLabel("ابحث عن").fill("ان");
  await expect(dialog.getByText("1 من 1")).toBeVisible();       // «إنّ» yes, «وإنتهى» no
  await dialog.getByRole("tab", { name: "في كامل المخطوط" }).click();
  await dialog.getByRole("button", { name: "ابحث في المخطوط" }).click();
  await expect(dialog.getByText("1 موضعاً في 1 وحدة")).toBeVisible();
  await dialog.locator(".find-hit").first().click();
  await expect(dialog).toBeHidden();
  // the editor takes focus on the next frame: poll instead of reading once
  await expect.poll(() => page.evaluate(() => window.getSelection()?.toString())).toBe("إنّ");
});
