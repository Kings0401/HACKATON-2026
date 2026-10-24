# SQL para tus tablas en español

1. En Supabase → SQL Editor, ejecuta **todo** [nclub_completo.sql](nclub_completo.sql). Funciona con las cinco tablas que compartiste y también en una base nueva. Agrega columnas, catálogo de servicios, credenciales seguras, eventos, funciones y políticas. Puedes repetirlo; no elimina tus datos.
2. Solo si quieres cargar los ejemplos, ejecuta [datos_demo.sql](datos_demo.sql). Mantiene a Valeria, Santiago, Camila, Daniel y Laura, y agrega `ADMIN001`. No sobrescribe registros existentes ni renueva membresías vencidas.
3. Crea cuentas en **Authentication → Users → Add user** para los miembros y el administrador. Define sus contraseñas allí. Vincula cada UUID ejecutando [vincular_cuenta.sql](vincular_cuenta.sql) con el ID de persona correcto.
4. Configura la URL y clave pública del proyecto en `.env.local` y reinicia Vite.
5. Para la recepción robótica, ejecuta [recepcion_robot.sql](recepcion_robot.sql) después de `nclub_completo.sql`. Agrega `robots`, `sesiones_atencion`, `eventos_identificacion`, `transcripciones`, `evidencias`, `rutas_compartidas` y `auditoria` (de solo inserción), con RLS: ADMIN lee y solo FastAPI escribe. También crea el bucket privado `evidencias-recepcion` y la política del canal Realtime privado `nclub:monitor`. Es aditivo y repetible. **Aún no se ha ejecutado en el proyecto remoto**; se probó en PostgreSQL embebido (`tests/robot-database.test.js`).

**No ejecutes las migraciones antiguas `migrations/001_nclub.sql`, `002_app_access.sql`, `seed.sql` ni `link-account.sql` con este esquema.** Corresponden a la versión anterior con tablas en inglés y se conservan como referencia histórica. La aplicación actual consulta las tablas en español.

El bloque `CREATE TABLE personas` estaba repetido en el SQL original. No hace falta volver a ejecutar ese bloque ni borrar ninguna tabla. `nclub_completo.sql` reutiliza las tablas existentes y agrega lo que falta. La categoría `ADMIN` permite gestionar el club y no se usa para decidir un ingreso físico.

## Acceso y datos existentes

- Solo VIP, REGULAR y ADMIN pueden tener sesión de aplicación. Invitados, personal y externos se gestionan desde administración. Incluso una cuenta de Auth vinculada por error a un visitante queda sin acceso a los datos ni a la emisión propia de QR.
- La membresía se comprueba por categoría, estado, actividad de la persona y `vigencia_hasta`. Activar una persona no renueva su membresía.
- Los códigos de prueba `NFC-VIP-001`, `QR-INV-001`, etc. se conservan como referencias. **No son los tokens seguros de la nueva app**. El QR de la app utiliza `emitir_credencial`: devuelve un token aleatorio una vez y guarda únicamente su hash en `credenciales`.
- `grupo_facial` se conserva como dato de clasificación. No registra consentimiento ni habilita captura o reconocimiento facial.
- `anfitrion_id` vincula las invitaciones a una persona real. Solo se completa automáticamente si el nombre coincide con un único miembro. Si no hay coincidencia inequívoca, completa ese ID como propietario antes de emitir el QR.
- Las reservas anteriores conservan sus fechas y duración. Solo se vinculan a un servicio cuando su destino coincide exactamente con el catálogo. Las reservas nuevas usan bloques de una hora, de 08:00 a 18:00 en Colombia, hasta 90 días y dentro de la vigencia de la membresía.
- Si existen reservas confirmadas que se solapan para una misma persona o recurso, la instalación se detiene y revierte completa. Revisa esos registros antes de repetirla; el script no cancela ni borra reservas para forzar la instalación.

Diagnóstico de relaciones pendientes, desde SQL Editor como propietario:

```sql
select id, persona_id, actividad, destino from public.reservas where servicio_id is null;
select codigo_qr, persona_id, anfitrion from public.invitaciones where anfitrion_id is null;
```

Las reservas sin servicio identificado se muestran como registros anteriores en la app: se pueden cancelar, pero no cambiar de horario hasta asignarles un servicio válido.

Las políticas se aplican por fila y columna. Los miembros no pueden leer códigos estáticos, promover su categoría, cambiar su vínculo de Auth ni escribir decisiones de acceso. Administración puede suspender personas, crear visitantes y revocar autorizaciones. Solo el backend con credencial privada escribe decisiones en `eventos_acceso` y vuelve a validar los permisos antes de ordenar acciones a los robots.

## Tablas y funciones

| Tabla | Uso |
| --- | --- |
| `personas` | Identidad y vínculo opcional a Auth |
| `membresias` | Nivel, estado y vigencia de miembros |
| `servicios` | Cinco canchas, restaurante y lounge |
| `reservas` | Reserva de una persona y recurso |
| `invitaciones` | Autorización de un invitado y anfitrión |
| `permisos_laborales` | Turno u orden, zona y acompañamiento |
| `credenciales` | Hash, vencimiento y revocación del token |
| `eventos_acceso` | Decisiones persistidas por FastAPI |

Funciones de la app: `consultar_disponibilidad`, `emitir_credencial`, `crear_visitante`, `actualizar_persona`. Todas validan la identidad autenticada; no conceden permisos basándose en lo que envíe el navegador.
