import { test, expect, type Page } from "@playwright/test";
async function guest(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Zugangscode", { exact: true }).fill("e2e-guest-code");
  await page.getByRole("button", { name: "Anmelden", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Was möchtest du finden?" }),
  ).toBeVisible();
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

test("Gast sucht, öffnet und lädt ein erlaubtes Dokument herunter", async ({
  page,
}) => {
  await guest(page);
  await page.getByLabel("Dokument-ID", { exact: true }).fill("101");
  await page.getByRole("button", { name: "Dokumente suchen" }).click();
  await page.getByRole("link", { name: /Rechnung Firma A/ }).click();
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
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: /Herunterladen/ }).click();
  expect((await download).suggestedFilename()).toBe("document-101.pdf");
  await page.goto("/documents/202");
  await expect(page.getByRole("alert")).toHaveText("Dokument nicht gefunden.");
  await expect(page.locator("canvas")).toHaveCount(0);
});

test("OIDC-Benutzer erhält erst nach manueller Freigabe Zugriff", async ({
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
    userPage.getByRole("heading", { name: "Dein Zugang wartet auf Freigabe" }),
  ).toBeVisible();
  await admin(adminPage);
  await adminPage
    .getByRole("button", { name: "Benutzer", exact: true })
    .click();
  const user = adminPage
    .locator("article")
    .filter({ has: adminPage.getByRole("heading", { name: "Anna Beispiel" }) });
  await user
    .getByRole("combobox", { name: "Freigabeprofil", exact: true })
    .selectOption({ label: "Firma A" });
  await user.getByRole("button", { name: "Benutzer speichern" }).click();
  await expect(adminPage.getByRole("status")).toHaveText(
    "Benutzerrechte gespeichert.",
  );
  await userPage.reload();
  await userPage.getByLabel("Dokument-ID", { exact: true }).fill("101");
  await userPage.getByRole("button", { name: "Dokumente suchen" }).click();
  await expect(
    userPage.getByRole("link", { name: /Rechnung Firma A/ }),
  ).toBeVisible();
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
  await a
    .getByRole("combobox", { name: "Freigabeprofil", exact: true })
    .selectOption({ label: "Ein Dokument" });
  await a.getByRole("button", { name: "Zugangscode erstellen" }).click();
  const code = await a.locator(".code-reveal code").innerText();
  await g.goto("/login");
  await g.getByLabel("Zugangscode", { exact: true }).fill(code);
  await g.getByRole("button", { name: "Anmelden", exact: true }).click();
  await expect(
    g.getByRole("heading", { name: "Was möchtest du finden?" }),
  ).toBeVisible();
  await g.goto("/documents/101");
  await expect(
    g.getByRole("heading", { name: "Rechnung Firma A" }),
  ).toBeVisible();
  a.once("dialog", (dialog) => dialog.accept());
  await a
    .getByRole("row")
    .filter({ hasText: "Browser-Test" })
    .getByRole("button", { name: "Widerrufen" })
    .click();
  await expect(a.getByRole("status")).toHaveText("Zugang widerrufen.");
  await g.reload();
  await expect(
    g.getByRole("heading", { name: "Willkommen zurück" }),
  ).toBeVisible();
  await adminContext.close();
  await guestContext.close();
});

test("Mobile Oberfläche bleibt bedienbar und ohne horizontalen Überlauf", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await guest(page);
  await page.getByLabel("Dokument-ID", { exact: true }).fill("101");
  await page.getByRole("button", { name: "Dokumente suchen" }).click();
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
