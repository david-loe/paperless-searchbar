import { test, expect, type Page } from "@playwright/test";
async function guest(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Zugangscode", { exact: true }).fill("e2e-guest-code");
  await page.getByRole("button", { name: "Anmelden", exact: true }).click();
  await expect(page.getByRole("search")).toBeVisible();
}
async function admin(page: Page) {
  await page.goto("/login");
  await expect(page.getByLabel("Benutzername")).toHaveCount(0);
  await expect(page.getByLabel("Passwort", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Lokaler Administrator" }),
  ).toHaveCount(0);
  await page.getByLabel("Zugangscode", { exact: true }).fill("e2e-admin-code");
  await page.getByRole("button", { name: "Anmelden", exact: true }).click();
  await page.getByRole("link", { name: "Verwaltung" }).click();
}

test("Gast sieht Downloads nur nach Freigabe seines Zugangscodes", async ({
  page,
  browser,
}) => {
  await guest(page);
  await page.getByLabel("Dokument-ID", { exact: true }).fill("101");
  await page.getByRole("button", { name: "Suchen", exact: true }).click();
  await expect(page).toHaveURL(/\/documents\/101$/);
  await expect(
    page.getByRole("heading", { name: "Rechnung Firma A" }),
  ).toBeVisible();
  await expect(page.getByRole("img", { name: "PDF-Seite 1" })).toBeVisible();
  await expect(page.locator(".pdf-canvas-container")).toHaveAttribute(
    "aria-busy",
    "false",
  );
  expect(
    await page.locator("canvas").evaluate((element: HTMLCanvasElement) => {
      const data = element
        .getContext("2d")!
        .getImageData(0, 0, element.width, element.height).data;
      let ink = 0;
      for (let i = 0; i < data.length; i += 4)
        if (data[i]! < 100 && data[i + 3]! > 0) ink++;
      return ink;
    }),
  ).toBeGreaterThan(100);
  await expect(
    page.getByRole("link", { name: "In Paperless bearbeiten" }),
  ).toHaveAttribute("href", "https://docs.example/documents/101/");
  await expect(page.getByRole("link", { name: /Herunterladen/ })).toHaveCount(
    0,
  );
  expect((await page.request.get("/api/documents/101/download")).status()).toBe(
    403,
  );
  const adminContext = await browser.newContext();
  const a = await adminContext.newPage();
  await admin(a);
  await a.getByRole("button", { name: "Zugangscodes", exact: true }).click();
  const permission = a.getByRole("checkbox", {
    name: "Download für Gastzugang erlauben",
    exact: true,
  });
  await expect(permission).not.toBeChecked();
  await permission.check();
  await expect(a.getByRole("status")).toHaveText(
    "Download-Einstellung gespeichert.",
  );
  await page.reload();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: /Herunterladen/ }).click();
  expect((await download).suggestedFilename()).toBe("document-101.pdf");
  await permission.uncheck();
  await expect(a.getByRole("status")).toHaveText(
    "Download-Einstellung gespeichert.",
  );
  expect((await page.request.get("/api/documents/101/download")).status()).toBe(
    403,
  );
  // The existing page picks up the new setting on the normal session refresh.
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("link", { name: /Herunterladen/ })).toHaveCount(
    0,
  );
  await expect(page.getByRole("img", { name: "PDF-Seite 1" })).toBeVisible();
  await adminContext.close();
  await page.goto("/documents/202");
  await expect(page.getByRole("alert")).toHaveText("Dokument nicht gefunden.");
  await expect(page.locator("canvas")).toHaveCount(0);
});

test("OIDC-Benutzer erhält Paperless-Rechte automatisch und Downloads separat", async ({
  browser,
}) => {
  const userContext = await browser.newContext(),
    adminContext = await browser.newContext();
  const userPage = await userContext.newPage(),
    adminPage = await adminContext.newPage();
  await userPage.goto("/login");
  await userPage
    .getByRole("link", { name: "Mit Organisationskonto anmelden" })
    .click();
  await expect(
    userPage.getByLabel("Dokument-ID", { exact: true }),
  ).toBeVisible();
  await admin(adminPage);
  await adminPage
    .getByRole("button", { name: "Benutzer", exact: true })
    .click();
  const user = adminPage
    .locator("article")
    .filter({ has: adminPage.getByRole("heading", { name: "Anna Beispiel" }) });
  await expect(user.getByText(/Paperless-Konto #11/)).toBeVisible();
  await expect(
    user.getByRole("combobox", { name: "Freigabeprofil" }),
  ).toHaveCount(0);
  await expect(
    user.getByLabel("Download erlauben", { exact: true }),
  ).not.toBeChecked();
  await user.getByRole("button", { name: "Benutzer speichern" }).click();
  await expect(adminPage.getByRole("status")).toHaveText(
    "Benutzerrechte gespeichert.",
  );
  await userPage.reload();
  await userPage.getByLabel("Dokument-ID", { exact: true }).fill("101");
  await userPage.getByRole("button", { name: "Suchen", exact: true }).click();
  await expect(
    userPage.getByRole("heading", { name: "Rechnung Firma A" }),
  ).toBeVisible();
  await expect(
    userPage.getByRole("link", { name: /Herunterladen/ }),
  ).toHaveCount(0);
  await user.getByLabel("Download erlauben", { exact: true }).check();
  await user.getByRole("button", { name: "Benutzer speichern" }).click();
  await expect(adminPage.getByRole("status")).toHaveText(
    "Benutzerrechte gespeichert.",
  );
  await userPage.reload();
  await expect(
    userPage.getByRole("link", { name: /Herunterladen/ }),
  ).toBeVisible();
  expect(
    (await userPage.request.get("/api/documents/101/download")).status(),
  ).toBe(200);
  await user.getByLabel("Download erlauben", { exact: true }).uncheck();
  await user.getByRole("button", { name: "Benutzer speichern" }).click();
  await expect(adminPage.getByRole("status")).toHaveText(
    "Benutzerrechte gespeichert.",
  );
  expect(
    (await userPage.request.get("/api/documents/101/download")).status(),
  ).toBe(403);
  await userPage.reload();
  await expect(
    userPage.getByRole("link", { name: /Herunterladen/ }),
  ).toHaveCount(0);
  await userContext.close();
  await adminContext.close();
});

test("Admin erstellt Profil und Code; Widerruf sperrt eine bestehende Sitzung", async ({
  browser,
}) => {
  const adminContext = await browser.newContext(),
    guestContext = await browser.newContext();
  const a = await adminContext.newPage(),
    g = await guestContext.newPage();
  await admin(a);
  await a.getByRole("button", { name: "Profil erstellen" }).click();
  await a.getByLabel("Profilname").fill("Ein Dokument");
  await a.getByLabel("Dokument-IDs", { exact: true }).fill("101");
  await a.getByRole("button", { name: "Profil speichern" }).click();
  await expect(a.getByRole("status")).toHaveText("Freigabeprofil gespeichert.");
  await a.getByRole("button", { name: "Zugangscodes", exact: true }).click();
  await a.getByLabel("Bezeichnung", { exact: true }).fill("Browser-Test");
  await expect(
    a.getByLabel("Download erlauben", { exact: true }),
  ).not.toBeChecked();
  await a.getByLabel("Download erlauben", { exact: true }).check();
  await a.getByRole("button", { name: "Zugangscode erstellen" }).click();
  await expect(
    a.getByText("Bitte eine Auswahl treffen.", { exact: true }),
  ).toBeVisible();
  await a
    .getByRole("searchbox", { name: "Freigabeprofil durchsuchen" })
    .fill("Ein Dokument");
  await a.getByRole("option", { name: "Ein Dokument", exact: true }).click();
  await a.getByRole("button", { name: "Zugangscode erstellen" }).click();
  const code = await a.locator(".code-reveal code").innerText();
  await expect(
    a.getByLabel("Download erlauben", { exact: true }),
  ).not.toBeChecked();
  await expect(
    a.getByLabel("Download für Browser-Test erlauben", { exact: true }),
  ).toBeChecked();
  await g.goto("/login");
  await g.getByLabel("Zugangscode", { exact: true }).fill(code);
  await g.getByRole("button", { name: "Anmelden", exact: true }).click();
  await expect(g.getByRole("search")).toBeVisible();
  await g.goto("/documents/101");
  await expect(
    g.getByRole("heading", { name: "Rechnung Firma A" }),
  ).toBeVisible();
  await expect(g.getByRole("link", { name: /Herunterladen/ })).toBeVisible();
  a.once("dialog", (dialog) => dialog.accept());
  await a
    .getByRole("row")
    .filter({ hasText: "Browser-Test" })
    .getByRole("button", { name: "Widerrufen" })
    .click();
  await expect(a.getByRole("status")).toHaveText("Zugang widerrufen.");
  await g.reload();
  await expect(g.getByLabel("Zugangscode", { exact: true })).toBeVisible();
  await adminContext.close();
  await guestContext.close();
});

test("Mobile Oberfläche bleibt bedienbar und ohne horizontalen Überlauf", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await guest(page);
  await page
    .getByRole("combobox", { name: "Speicherpfad", exact: true })
    .click();
  await page.getByRole("option", { name: "Buchhaltung", exact: true }).click();
  await page.getByRole("button", { name: "Suchen", exact: true }).click();
  await expect(
    page.getByRole("link", { name: /Rechnung Firma A/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/mobile-search.png",
    fullPage: true,
  });
});

test("Admin bestimmt direkte Suchfelder; Gäste suchen ausschließlich exakt", async ({
  browser,
}) => {
  const adminContext = await browser.newContext();
  const guestContext = await browser.newContext();
  const a = await adminContext.newPage();
  const g = await guestContext.newPage();
  await admin(a);
  await a.getByRole("button", { name: "Suchfelder", exact: true }).click();
  await a.getByLabel("Mandant", { exact: true }).check();
  await a.getByLabel("Bezahlt", { exact: true }).check();
  await a.getByLabel("Kategorie", { exact: true }).check();
  await a.getByRole("button", { name: "Suchfelder speichern" }).click();
  await expect(a.getByRole("status")).toHaveText("Suchfelder gespeichert.");
  await a.reload();
  await a.getByRole("button", { name: "Suchfelder", exact: true }).click();
  await expect(a.getByLabel("Mandant", { exact: true })).toBeChecked();
  await guest(g);
  await expect(g.getByRole("heading")).toHaveCount(0);
  await expect(g.getByPlaceholder("Auswahl filtern …")).toHaveCount(0);
  await expect(
    g.getByRole("button", { name: /Custom Field hinzufügen/ }),
  ).toHaveCount(0);
  await expect(g.getByLabel("Mandant", { exact: true })).toBeVisible();
  await expect(g.getByLabel("Betrag", { exact: true })).toHaveCount(0);
  await g.getByLabel("Mandant", { exact: true }).fill("A");
  const request = g.waitForRequest((r) =>
    r.url().endsWith("/api/documents/search"),
  );
  await g.getByRole("button", { name: "Suchen", exact: true }).click();
  expect((await request).postDataJSON().custom_fields).toEqual([
    { field: 1, op: "exact", value: "A" },
  ]);
  await expect(g.getByRole("link", { name: /Rechnung Firma A/ })).toBeVisible();
  await g.getByLabel("Mandant", { exact: true }).fill("a");
  await g.getByRole("button", { name: "Suchen", exact: true }).click();
  await expect(
    g.getByText("Keine passenden Dokumente.", { exact: true }),
  ).toBeVisible();
  await g.getByRole("button", { name: "Zurücksetzen" }).click();
  await expect(g.getByLabel("Mandant", { exact: true })).toHaveValue("");
  await g.getByLabel("Dokument-ID", { exact: true }).fill("202");
  await g.getByRole("button", { name: "Suchen", exact: true }).click();
  await expect(
    g.getByText("Keine passenden Dokumente.", { exact: true }),
  ).toBeVisible();
  await expect(g).toHaveURL(/\/$/);
  await g.getByRole("button", { name: "Zurücksetzen" }).click();
  await g.setViewportSize({ width: 390, height: 844 });
  expect(
    await g.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBe(true);
  await g.screenshot({
    path: "test-results/mobile-search-fields.png",
    fullPage: true,
  });
  await g.setViewportSize({ width: 1440, height: 900 });
  await g.screenshot({
    path: "test-results/desktop-search-fields.png",
    fullPage: true,
  });
  await adminContext.close();
  await guestContext.close();
});

test("Dokumenttyp, beschriftete Treffer, echte Thumbnails und mobile Dropdowns", async ({
  page,
}) => {
  await guest(page);
  let searchRequests = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/documents/search")) searchRequests++;
  });
  const type = page.getByRole("combobox", { name: "Dokumenttyp", exact: true });
  await type.click();
  const query = page.getByRole("searchbox", {
    name: "Dokumenttyp durchsuchen",
  });
  await expect(query).toBeFocused();
  await query.fill("Vertrag");
  await expect(
    page.getByText("Keine passenden Einträge.", { exact: true }),
  ).toBeVisible();
  await query.fill("RECHN");
  await query.press("ArrowDown");
  await query.press("Enter");
  await expect(type).toContainText("Rechnung");
  expect(searchRequests).toBe(0);
  const search = page.waitForRequest((request) =>
    request.url().endsWith("/api/documents/search"),
  );
  await page.getByRole("button", { name: "Suchen", exact: true }).click();
  expect((await search).postDataJSON().document_type).toBe(1);
  const result = page.getByRole("link", { name: /Rechnung Firma A/ });
  await expect(result).toBeVisible();
  await expect(result.locator("dt")).toContainText([
    "Dokument-ID",
    "Datum",
    "Dokumenttyp",
    "Korrespondent",
    "Speicherpfad",
  ]);
  await expect(result.locator("dd")).toContainText([
    "#101",
    "01.10.2026",
    "Rechnung",
    "Firma A",
    "Buchhaltung",
  ]);
  const thumbnail = result.getByRole("img", {
    name: "Vorschau: Rechnung Firma A",
    exact: true,
  });
  await expect(thumbnail).toBeVisible();
  await expect
    .poll(() => thumbnail.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBe(96);
  await page.screenshot({
    path: "test-results/desktop-results.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/mobile-results.png",
    fullPage: true,
  });
  await type.click();
  await expect(query).toHaveValue("");
  await query.fill("re");
  await expect(type).toContainText("Rechnung");
  await page.screenshot({
    path: "test-results/mobile-dropdown.png",
    fullPage: true,
  });
  await query.press("Escape");
  await expect(type).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Zurücksetzen" }).click();
  await expect(type).toHaveText("Alle⌄");
  await page
    .getByRole("combobox", { name: "Speicherpfad", exact: true })
    .click();
  await page.getByRole("option", { name: "Buchhaltung", exact: true }).click();
  await page.route("**/api/documents/101/thumb", (route) =>
    route.fulfill({ status: 404, body: "" }),
  );
  await page.getByRole("button", { name: "Suchen", exact: true }).click();
  await expect(
    result.getByRole("img", {
      name: "Keine Miniaturansicht verfügbar",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    result.getByRole("heading", { name: "Rechnung Firma A" }),
  ).toBeVisible();
  await result.click();
  await expect(page).toHaveURL(/\/documents\/101$/);
  await expect(
    page.locator("dt").filter({ hasText: /^Dokumenttyp$/ }),
  ).toBeVisible();
});

test("Verwaltungslisten erlauben Mehrfachauswahl und durchsuchbare Custom-Field-Werte", async ({
  page,
}) => {
  await admin(page);
  await page.getByRole("button", { name: "Profil erstellen" }).click();
  await page.getByLabel("Profilname", { exact: true }).fill("Suchbare Listen");
  const people = page.getByRole("combobox", {
    name: "Erlaubte Korrespondenten",
    exact: true,
  });
  await people.click();
  await page
    .getByRole("searchbox", { name: "Erlaubte Korrespondenten durchsuchen" })
    .fill("Firma A");
  await page.getByRole("option", { name: "Firma A", exact: true }).click();
  await page
    .getByRole("searchbox", { name: "Erlaubte Korrespondenten durchsuchen" })
    .fill("Firma B");
  await page.getByRole("option", { name: "Firma B", exact: true }).click();
  await page
    .getByRole("searchbox", { name: "Erlaubte Korrespondenten durchsuchen" })
    .press("Escape");
  await expect(people).toContainText("Firma A, Firma B");
  await page.getByRole("button", { name: /Custom Field hinzufügen/ }).click();
  await page.getByRole("combobox", { name: "Feld", exact: true }).click();
  await page
    .getByRole("searchbox", { name: "Feld durchsuchen" })
    .fill("kategorie");
  await page.getByRole("option", { name: "Kategorie", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Bedingung", exact: true })
    .selectOption("in");
  await page.getByRole("combobox", { name: "Wert", exact: true }).click();
  await page
    .getByRole("searchbox", { name: "Wert durchsuchen" })
    .fill("Allgemein");
  await page.getByRole("option", { name: "Allgemein", exact: true }).click();
  await page
    .getByRole("searchbox", { name: "Wert durchsuchen" })
    .press("Escape");
  await page.getByRole("button", { name: "Profil speichern" }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Freigabeprofil gespeichert.",
  );
  await page
    .locator("article")
    .filter({
      has: page.getByRole("heading", { name: "Suchbare Listen", exact: true }),
    })
    .getByRole("button", { name: "Bearbeiten" })
    .click();
  await expect(people).toContainText("Firma A, Firma B");
  await expect(
    page.getByRole("combobox", { name: "Wert", exact: true }),
  ).toContainText("Allgemein");
});
