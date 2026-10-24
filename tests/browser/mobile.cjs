async (page) => {
  const errors = [];
  page.on("pageerror", (err) => errors.push(err.message));
  const assert = (value, message) => {
    if (!value) throw new Error(message);
  };
  const report = [];
  await page.goto("http://127.0.0.1:5173/#/demo");
  await page.getByRole("button", { name: /Gabriela Montenegro/ }).click();
  await page
    .getByRole("heading", { name: "Bienvenida de nuevo, Gabriela." })
    .waitFor();
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    "VIP horizontal overflow",
  );
  await page.screenshot({
    path: "output/playwright/vip-mobile.png",
    fullPage: true,
  });
  await page
    .getByRole("navigation", { name: "Navegación móvil" })
    .getByRole("link", { name: "Reservar", exact: true })
    .click();
  await page.getByRole("button", { name: "Ver horarios" }).first().click();
  await page
    .locator(".time-slot")
    .filter({ has: page.locator("input:not(:disabled)") })
    .first()
    .click();
  await page.getByRole("button", { name: "Confirmar reserva" }).click();
  await page.waitForURL("**/bookings?tab=mine");
  assert(
    (await page.locator(".reservation-card").count()) >= 2,
    "Booking not created",
  );
  const count = await page.locator(".reservation-card").count();
  await page.reload();
  await page
    .getByRole("heading", { name: "Tu próxima experiencia." })
    .waitFor();
  assert(
    (await page.locator(".reservation-card").count()) === count,
    "Booking not persistent",
  );
  report.push("VIP booking created and persisted after reload");
  await page.getByRole("button", { name: "Modificar" }).last().click();
  await page
    .locator(".time-slot")
    .filter({ has: page.locator("input:not(:disabled)") })
    .last()
    .click();
  await page.getByRole("button", { name: "Guardar cambio" }).click();
  await page.waitForFunction(() => !document.querySelector("#modal").open);
  await page
    .getByRole("button", { name: "Cancelar", exact: true })
    .last()
    .click();
  await page
    .getByRole("button", { name: "Cancelar reserva", exact: true })
    .click();
  await page.waitForFunction(() => !document.querySelector("#modal").open);
  assert(
    (await page.locator(".my-reservations").innerText()).includes("Cancelada"),
    "Cancellation not visible",
  );
  report.push("Reservation modified and cancelled");
  await page
    .getByRole("navigation", { name: "Navegación móvil" })
    .getByRole("link", { name: "Credencial", exact: true })
    .click();
  await page.getByRole("button", { name: "Generar credencial QR" }).click();
  await page.locator("#credential-qr:not(.hidden)").waitFor();
  assert(
    await page.locator("#credential-qr").evaluate((el) => el.width > 200),
    "QR canvas empty",
  );
  await page.screenshot({
    path: "output/playwright/credential-mobile.png",
    fullPage: true,
  });
  report.push("QR credential generated");
  await page.getByRole("link", { name: "Cambiar perfil" }).click();
  await page.getByRole("button", { name: /Alejandro Ríos/ }).click();
  await page
    .getByRole("navigation", { name: "Navegación móvil" })
    .getByRole("link", { name: "Reservar", exact: true })
    .click();
  await page.getByRole("link", { name: "Lounge VIP", exact: true }).click();
  assert(
    (await page.getByRole("button", { name: "Ver horarios" }).count()) === 0,
    "Regular can book VIP lounge",
  );
  assert(
    (await page.locator(".services-grid").innerText()).includes(
      "Exclusivo VIP",
    ),
    "VIP lock absent",
  );
  await page.goto("http://127.0.0.1:5173/#/admin");
  await page.waitForURL("**/dashboard");
  report.push("Regular lounge restriction and admin route guard");
  await page.getByRole("link", { name: "Cambiar perfil" }).click();
  await page.getByRole("button", { name: /Sofía Restrepo/ }).click();
  await page
    .getByRole("link", { name: "Smart Reception", exact: false })
    .first()
    .click();
  for (const [label, role] of [
    ["Simular VIP", "VIP"],
    ["Simular Miembro", "REGULAR"],
    ["Simular Invitado", "GUEST"],
    ["Simular Personal", "STAFF"],
    ["Simular Externo", "EXTERNAL"],
  ]) {
    await page.getByRole("button", { name: label, exact: false }).click();
    await page.waitForFunction(
      () =>
        document.querySelector('[data-action="simulate"]:not(:disabled)') &&
        document.querySelector(".flow-steps .done:last-child"),
      {},
      { timeout: 15000 },
    );
    if (role === "VIP")
      await page
        .getByText("Transferencia VIP completada", { exact: false })
        .waitFor();
    assert(
      (await page.locator(".reception-visitor").innerText()).includes(
        "Autorizado",
      ),
      `${role} not authorized in DEMO`,
    );
    report.push(`${role} reception flow complete`);
  }
  await page.locator("#simulation-outcome").selectOption("denied");
  await page.getByRole("button", { name: "Simular VIP", exact: false }).click();
  await page.waitForFunction(() =>
    document.querySelector('[data-action="simulate"]:not(:disabled)'),
  );
  assert(
    (await page.locator(".reception-visitor").innerText()).includes("Denegado"),
    "Denied state missing",
  );
  await page.locator("#simulation-outcome").selectOption("review");
  await page
    .getByRole("button", { name: "Simular Miembro", exact: false })
    .click();
  await page.waitForFunction(() =>
    document.querySelector('[data-action="simulate"]:not(:disabled)'),
  );
  assert(
    (await page.locator(".reception-visitor").innerText()).includes(
      "Revisión requerida",
    ),
    "Review state missing",
  );
  report.push("Denied and review flows verified");
  await page.screenshot({
    path: "output/playwright/reception-mobile.png",
    fullPage: true,
  });
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    "Reception horizontal overflow",
  );
  assert(errors.length === 0, `Page errors: ${errors.join("; ")}`);
  console.log(JSON.stringify({ passed: report, pageErrors: errors }, null, 2));
};
