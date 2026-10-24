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

## Integración robot, visión, backend y mapa (24 de octubre de 2026)

En esta iteración no se usó Playwright. La comprobación visual se hizo con capturas de Edge sin interfaz (`--screenshot`) a 1280, 390 y 320 px.

| Suite | Resultado | Qué cubre |
| --- | --- | --- |
| `npm test` | **55/55** | Las 46 previas más el RLS del esquema robótico en PGlite (servidor escribe, ADMIN lee, miembro y anónimo no ven nada, auditoría inmutable, decisión autorizada exige identidad) y la paridad de rutas JS/Python en 270 combinaciones |
| `backend: pytest` | **46/46** | Cinco flujos diferenciados, rostro de otra persona, similitud baja, rostro sin credencial, `demo_`, revocaciones, anfitrión inactivo, token seguro, persistencia fallida → revisión, idempotencia, registros, autenticación ADMIN/robot, stream, `/rostros` con espacios y paréntesis, contrato original `/resolve-access`, `/validate` de un solo uso, simulación, ruta compartida |
| `vision: pytest` | **9/9** | QR (seguro, estático, DEMO, dentro de una escena), conversión `rgb8`/JPEG, identificación de las 5 identidades, rechazo de un no registrado, exclusión de fotos duplicadas |
| `robot_agent: pytest` | **7/7** | Agente real contra el backend real en memoria: 5 flujos de extremo a extremo con rostros reales del dataset, casos sin rostro → revisión, backend caído, reconexión, VAD de AimDK y por energía, QR no repetido |
| `npm run build` | Aprobado | |

Verificado además:

- Sincronización de rostros contra el **Storage real** con el backend nuevo: 18/18 fotografías, 0 errores (solo lectura).
- Simulador por HTTP real (uvicorn, modo memoria): VIP → VIP Lounge con AGIBOT 02, miembro → Cancha 2, invitado → Restaurante, personal → Oficina, proveedor → Zona técnica con acompañamiento.
- Panel `#/admin/robots` alimentado por `/robot/monitor` real: cámara MJPEG privada en vivo, micrófono, transcripción, validaciones, decisión, ruta e historial.
- Recepción DEMO: escenario VIP con mapa, pasos y QR, y página `#/ruta` a 390 y 320 px sin desbordamiento horizontal.

No verificado: robot físico, topics reales, TTS, ASR con audio real (faster-whisper/Vosk no se instalaron), imagen Docker (Docker Desktop detenido), `recepcion_robot.sql` en el proyecto remoto, Realtime privado remoto y JWT ADMIN real (no hay cuenta ADMIN vinculada).
