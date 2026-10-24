async (page) => {
  const errors = [];
  page.on("pageerror", (err) => errors.push(err.message));
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const suffix = Date.now().toString(36),
    guestName = `Valentina Invitada ${suffix}`;
  await page.goto("http://127.0.0.1:5173/#/admin/invitations");
  await page.getByRole("button", { name: "Nueva invitación" }).click();
  await page.getByRole("dialog").getByLabel("Nombre completo").fill(guestName);
  await page.getByRole("button", { name: "Crear y generar QR" }).click();
  await page.locator("#visitor-qr").waitFor();
  assert(
    await page.locator("#visitor-qr").evaluate((c) => c.width > 200),
    "Guest QR was not drawn",
  );
  await page.getByRole("button", { name: "Cerrar", exact: true }).click();
  const guest = page.getByRole("row").filter({ hasText: guestName });
  await guest.getByRole("button", { name: "Revocar", exact: true }).click();
  await page
    .getByRole("button", { name: "Revocar permiso", exact: true })
    .click();
  await page.waitForFunction(() => !document.querySelector("#modal").open);
  assert(
    (await guest.innerText()).includes("Revocada"),
    "Invitation not revoked",
  );
  await page.goto("http://127.0.0.1:5173/#/admin/work");
  for (const [role, name, zone] of [
    ["EXTERNAL", `Contratista ${suffix}`, "MAINTENANCE"],
    ["STAFF", `Personal ${suffix}`, "KITCHEN"],
  ]) {
    await page.getByRole("button", { name: "Nuevo turno u orden" }).click();
    await page.getByRole("dialog").getByLabel("Nombre completo").fill(name);
    await page
      .getByRole("dialog")
      .getByRole("combobox", { name: "Tipo", exact: true })
      .selectOption(role);
    await page
      .getByRole("dialog")
      .getByLabel("Empresa", { exact: true })
      .fill("N Club Test");
    await page.getByRole("button", { name: "Crear y generar QR" }).click();
    await page.locator("#visitor-qr").waitFor();
    await page.getByRole("button", { name: "Cerrar", exact: true }).click();
    assert(
      (
        await page.getByRole("row").filter({ hasText: name }).innerText()
      ).includes(zone),
      `${role} wrong zone`,
    );
  }
  await page.goto("http://127.0.0.1:5173/#/admin/users");
  await page
    .getByRole("searchbox", { name: "Buscar usuarios" })
    .fill("Isabella");
  const person = page.getByRole("row").filter({ hasText: "Isabella Vargas" });
  await person
    .getByRole("button", { name: "Editar Isabella Vargas", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Nombre completo")
    .fill("Isabella Vargas");
  await page.getByRole("button", { name: "Guardar cambios" }).click();
  await page.waitForFunction(() => !document.querySelector("#modal").open);
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ["admin", "admin/users", "admin/work", "reception"]) {
      await page.goto(`http://127.0.0.1:5173/#/${route}`);
      await page.locator("main h1").waitFor();
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `Overflow: ${route} @ ${width}`,
      );
    }
  }
  await page.screenshot({ path: "output/playwright/reception-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  for (const name of ["Isabella Vargas", "Camila Torres", "Daniel Medina"]) {
    await page.goto("http://127.0.0.1:5173/#/demo");
    await page.getByRole("button", { name: new RegExp(name) }).click();
    await page.getByRole("heading", { name: "Tu identificación" }).waitFor();
    assert(
      (await page
        .getByRole("navigation", { name: "Navegación móvil" })
        .getByRole("link", { name: "Reservar", exact: true })
        .count()) === 0,
      `${name} has member services`,
    );
    await page
      .getByRole("navigation", { name: "Navegación móvil" })
      .getByRole("link", { name: "Credencial", exact: true })
      .click();
    await page.getByRole("button", { name: "Generar credencial QR" }).click();
    await page.locator("#credential-qr:not(.hidden)").waitFor();
  }
  await page.goto("http://127.0.0.1:5173/#/");
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      `Landing overflow @ ${width}`,
    );
    assert(
      await page
        .locator(".hero-image")
        .evaluate((img) => img.complete && img.naturalWidth > 0),
      "Hero image missing",
    );
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "output/playwright/landing-mobile.png" });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: "output/playwright/landing-desktop.png" });
  assert(errors.length === 0, errors.join("; "));
  return {
    passed: [
      "guest creation and QR",
      "invitation revocation",
      "external work order",
      "staff shift",
      "profile edit",
      "five admin views at 4 screen widths",
      "three non-member dashboards and QR",
      "landing photos and responsive layout",
    ],
    errors,
  };
};
