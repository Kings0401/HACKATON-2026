# Validación del MVP

Comprobación local realizada el 23 de octubre de 2026.

## Automatizada

`npm test`: **22 pruebas aprobadas**. Incluye una instancia PostgreSQL embebida (PGlite, con pgcrypto y btree_gist) que aplica la migración y el seed completos. Se emula únicamente la identidad de Supabase Auth para probar RLS; no se afirma haber conectado un proyecto remoto.

Cobertura: aislamiento de perfiles/reservas, bloqueo de promoción a ADMIN, restricción VIP en servidor, imposibilidad de falsificar accesos desde el navegador, ocultación de hashes, disponibilidad sin identidades ajenas, exclusiones de horarios, emisión/rotación de tokens, invitaciones sin cuenta, permisos de zona externa, invitaciones futuras, cancelación y fechas de Colombia. Pruebas adicionales de escenarios DEMO y de validación del contrato FastAPI.

`npm run build`: compilación de producción aprobada.

## Navegador real

Playwright CLI, Chromium, experiencia principal a 390 × 844 px:

- Landing, acceso DEMO y dashboard VIP.
- Crear reserva, recargar y comprobar persistencia, modificar y cancelar.
- Generar y mostrar QR escaneable en canvas.
- Miembro regular: Lounge VIP bloqueado y acceso a administración rechazado.
- Cinco recorridos de recepción aprobados, incluido handoff VIP a robot2.
- Escenarios denegado y revisión requerida.
- Crear invitación sin cuenta, generar QR y revocar.
- Crear turno STAFF y orden EXTERNAL con zonas diferentes.
- Editar perfil desde administración y buscar usuarios.
- Dashboards de invitado, personal y externo; QR y ausencia de reservas de miembros.
- Landing y paneles administrativos/reception sin desbordamiento horizontal a 320, 390, 768 y 1440 px.
- Sin errores de JavaScript en los recorridos aprobados.

Para repetir, iniciar Vite y utilizar los scripts de `tests/browser` con una sesión de Playwright CLI. Primero ejecutar el recorrido móvil; deja una sesión ADMIN DEMO preparada para el recorrido administrativo:

```powershell
npx --package @playwright/cli playwright-cli --session nclub open http://127.0.0.1:5173 --headed
npx --package @playwright/cli playwright-cli --session nclub resize 390 844
npx --package @playwright/cli playwright-cli --session nclub run-code --filename tests/browser/mobile.cjs
npx --package @playwright/cli playwright-cli --session nclub run-code --filename tests/browser/admin.cjs
```

Las pruebas de navegador modifican únicamente el almacén DEMO local. Capturas en `output/playwright/` (ignorado por Git).

## Pendiente del entorno del equipo

- Conexión remota Supabase: faltan URL y clave pública del proyecto.
- Supabase Auth real: faltan cuentas creadas y vinculadas a los perfiles.
- Realtime remoto y su configuración/publicación.
- FastAPI real: falta URL operativa, JWT y endpoints del compañero.
- SDK/comandos físicos AGIBOT y reconocimiento facial voluntario.

Los contratos y procedimientos están en README y `docs/FASTAPI.md`. Las pruebas locales no sustituyen la verificación de estos servicios reales.
