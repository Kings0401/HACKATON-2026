# Contrato de integración — FastAPI y AGIBOT

FastAPI es la única autoridad de identificación y acceso físico. El navegador presenta resultados; no prueba una identidad enviando un rol. Las simulaciones no emiten comandos físicos.

## Implementación incluida (`backend/`)

Este contrato está implementado en `backend/app` (reorganización de `nclub-backend.zip/main.py`): `routers/` (public, robot, admin), `services/` (access, reception, navigation, dialogue), `repository.py` (Supabase) y `memory_repo.py` (datos ficticios para pruebas y simulación).

```powershell
cd backend
python -m venv .venv; .venv\Scripts\activate
pip install -r requirements.txt
python -c "from app.services.speaker_id import warmup; warmup()"  # descarga el modelo ECAPA antes de abrir recepción
Copy-Item .env.example .env   # completar claves de servidor
uvicorn app.main:app --reload --port 8000
pytest
```

| Endpoint | Autenticación | Uso |
| --- | --- | --- |
| `GET /health`, `GET /` | Pública | Estado; indica `simulation` en modo memoria |
| `GET /navigation/map` | Pública | Grafo esquemático (simulado) del club |
| `GET /navigation/shared/{token}` | Token de la ruta | Ruta para el celular; solo lectura, vence en 30 min |
| `POST /resolve-access` | X-Robot-Key | **Contrato original** conservado (`face_group` + `credential_code`) |
| `GET /rostros`, `/rostros/{id}`, `/rostros/{id}/{archivo}` | X-Robot-Key | Fotografías de registro; corrige los 404 (ver `docs/VISION.md`) |
| `POST /robot/{robot_id}/heartbeat` | X-Robot-Key | Estado de cámara/micrófono, modelo y firmware |
| `PUT /robot/{robot_id}/frame` | X-Robot-Key | Último JPEG para el stream (solo memoria, ≤ 600 KB) |
| `POST /robot/sessions` | X-Robot-Key | Inicia una sesión de atención |
| `POST /robot/sessions/{id}/faces` | X-Robot-Key | Candidato facial `{persona_id, similarity, …}` |
| `POST /robot/sessions/{id}/credentials` | X-Robot-Key | QR, carné o NFC leído (se registra enmascarado) |
| `POST /robot/sessions/{id}/utterances` | X-Robot-Key | Transcripción en español y audio WAV transitorio del robot para verificar al locutor; el audio biométrico no se archiva |
| `POST /robot/sessions/{id}/evidence` | X-Robot-Key | Fotograma puntual, solo con `STORE_EVIDENCE` y consentimiento |
| `POST /robot/sessions/{id}/resolve` | X-Robot-Key | Decisión + checks + ruta + QR + texto para TTS (idempotente) |
| `POST /robot/sessions/{id}/close` | X-Robot-Key | Cierra la sesión |
| `GET /robot/monitor` | JWT ADMIN | Panel `#/admin/robots` (ver abajo; campos ampliados) |
| `GET /robot/stream/{robot_id}.mjpeg?token=` | Token HMAC corto | Cámara en vivo privada |
| `GET /admin/sessions`, `GET /admin/evidence/{id}` | JWT ADMIN | Historial y URL firmadas de evidencias (auditado) |
| `POST /validate`, `POST /access/check` | JWT ADMIN | Verificación real (validation_id de un solo uso) y simulación |
| `GET /vip/context/{id}` | JWT ADMIN | Contexto mínimo para AGIBOT 02 |
| `POST /events` | JWT miembro | Solo `assistance_requested` |
| `POST /navigation/route` | JWT ADMIN | Calcular una ruta por categoría y destino |
| `GET /admin/lab/status`, `POST /admin/lab/frame` (JPEG), `/admin/lab/text`, `/admin/lab/reset`, `/admin/lab/reload` | JWT ADMIN | Robot simulado con la cámara del dispositivo (mismo agente del robot) |
| `POST /admin/members` | JWT ADMIN | Alta de miembro VIP/REGULAR con membresía; devuelve un QR seguro |
| `POST /admin/personas/{id}/photos?consent=true` | JWT ADMIN | Foto de registro facial (1 rostro, sin EXIF) → Storage privado + galería |
| `POST /admin/personas/{id}/voice?consent=true` | JWT ADMIN | Muestra WAV mono 16 kHz; registro privado para verificar la voz con SpeechBrain ECAPA-TDNN |
| `GET /admin/personas/{id}/biometrics` | JWT ADMIN | Previsualizaciones firmadas de foto y audio del bucket privado |
| `POST /admin/personas/{id}/voice?sample_id=1..3&consent=true` | JWT ADMIN | Registra cada una de tres frases guiadas WAV; se reemplaza solo la frase del mismo numero |
| `POST /admin/personas/{id}/voice/verify?consent=true` | JWT ADMIN | Compara una frase transitoria con las tres muestras; exige mayoria de coincidencias y no guarda el audio de prueba |
| `POST /admin/personas/{id}/credential` | JWT ADMIN | QR seguro temporal de un miembro |

Respuesta de `resolve` (y de `access/check`): campos del contrato más `decision` (`AUTORIZADO`, `DENEGADO`, `REVISION`, `ACOMPANAMIENTO`), `category`, `methods`, `checks[]` (`name`, `ok`, `detail`), `escort_required`, `route` (ruta, pasos, `share_url`) y `speech`. Un proveedor con acompañamiento devuelve `access:"pending"`.

**Reglas aplicadas**: cada categoría combina el rostro con su propio factor. VIP: rostro + voz enrolada, sin credencial y con trato preferencial. Regular: rostro + nombre completo + últimos cuatro dígitos del documento + voz enrolada, sin credencial; la verificación es estricta (cada dato debe decirse con la voz registrada y al tercer intento fallido pasa a revisión). Cuando la identificación de un socio queda completa, `/utterances` responde `ready: true` y el robot pide la decisión. Invitado, personal y proveedor: credencial obligatoria (token `nclub:v1:` → hash en `credenciales`, o código estático de demostración si `ALLOW_STATIC_CREDENTIALS=true`; `demo_` siempre se rechaza). El rostro es obligatorio para VIP, regular, personal y proveedor (`FACE_REQUIRED_CATEGORIES`) y opcional para el invitado, pero si corresponde a otra persona → revisión. Miembros: membresía y reserva en la ventana de llegada (tolerancia de 60 min). Invitados: invitación vigente + anfitrión con membresía vigente (si no, revisión). Personal y proveedores: permiso vigente; acompañamiento → `ACOMPANAMIENTO`. La decisión se registra en `eventos_acceso` **antes** de responder; si falla, se responde revisión.

## Configuración del servidor

- Permitir CORS exclusivamente para los orígenes de Vite usados por el equipo (`http://127.0.0.1:5173`, `http://localhost:5173` y, al probar teléfono, la IP LAN explícita), y el dominio HTTPS final. Métodos GET/POST; cabeceras Authorization y Content-Type.
- Validar `Authorization: Bearer <Supabase access_token>` criptográficamente mediante JWKS del proyecto o `supabase.auth.get_user(token)`. Consultar `personas.auth_user_id` por el `sub` verificado. No confiar en `role`, `visitor_id`, metadata de Auth o `simulation` sin permisos del actor.
- Endpoints de recepción/simulación solo para un ADMIN activo o identidad de robot autenticada por el servidor. El navegador nunca recibe el secreto del robot.
- Usar `SUPABASE_URL` y una credencial de servidor **solo en FastAPI**. Una service_role omite RLS: revalidar explícitamente permisos y campos antes de cualquier operación. No exponer un proxy genérico de escritura ni aceptar decisiones arbitrarias de `/events`.
- Los errores deben usar códigos HTTP adecuados y `{"detail":"mensaje comprensible"}` sin tokens, secretos ni datos de otros miembros.

## Endpoints

### GET /health

Público, sin información sensible. Respuesta: `{"status":"ok","database":"supabase"}`. El cliente usa timeout de 10 segundos.

### GET /robot/monitor

Solo ADMIN activo. La pantalla `#/admin/robots` consulta este endpoint cada 3 segundos y espera una respuesta con esta forma:

```json
{
  "connected": true,
  "robot_name": "AGIBOT recepción",
  "updated_at": "2026-10-24T15:00:00Z",
  "camera_stream_url": "https://api.example/robot/stream?token=URL_FIRMADA_CORTA",
  "last_heard": {
    "transcript": "Buenos días, tengo una reserva",
    "language": "es-CO",
    "robot_name": "AGIBOT recepción",
    "audio_url": "https://api.example/robot/audio/CLIP?token=URL_FIRMADA_CORTA"
  },
  "events": [
    {
      "created_at": "2026-10-24T15:00:00Z",
      "display_name": "Visitante",
      "role": "VIP",
      "method": "facial + voz",
      "access": "review",
      "robot_name": "AGIBOT recepción"
    }
  ]
}
```

`camera_stream_url` debe ser un stream privado de solo lectura (por ejemplo MJPEG para la vista web), con token de corta duración porque el elemento `<img>` del navegador no puede adjuntar el JWT de la sesión. El token debe limitarse al stream y expirar pronto. Los clips también deben usar URL temporal; no devolver audio de otras interacciones. No retransmitir un feed público ni incluir identificadores biométricos. `events` contiene únicamente los campos mínimos de auditoría; la categoría devuelta es la decisión del backend, no una clasificación del navegador. Si el endpoint no está configurado, la interfaz indica que el robot está desconectado.

Para reconocimiento facial, solicitar consentimiento y enrolamiento revocable, y devolver una coincidencia candidata con su nivel de confianza; una coincidencia facial o de voz por sí sola nunca concede ingreso ni acredita categoría VIP. La voz VIP debe comprobarse contra una credencial/enrolamiento autorizado y, ante duda, pasar a revisión o QR. Registrar método, rol candidato, decisión final y motivo sin guardar audio o imágenes salvo necesidad y política explícitas.

### POST /recognition

Preparado en `src/api.js`; no se envían imágenes faciales desde el MVP.

Requiere captura del dispositivo confiable, consentimiento facial explícito, enrolamiento previo revocable y un método alternativo QR. Debe devolver una identidad candidata o referencia de identificación, **nunca autorizar por sí solo**. No registrar biometría ni inferir categoría VIP por aspecto físico. No guardar plantillas biométricas en tablas públicas.

### POST /validate

La pantalla ADMIN real envía:

```json
{
  "credential_token": "64 caracteres hexadecimales opacos",
  "method": "qr",
  "simulation": false
}
```

El lector quita `nclub:v1:` del QR antes de enviar. FastAPI calcula SHA-256 del token como UTF-8 (igual a `encode(digest(token,'sha256'),'hex')`), consulta `credenciales.token_hash` con credencial de servidor y comprueba `expira_en` y `revocada_en`. Rechazar siempre tokens con prefijo `demo_` en el canal real. Los códigos estáticos originales (`NFC-VIP-001`, `QR-INV-001`, etc.) no son tokens de la app ni deben aceptarse como si fueran los tokens aleatorios emitidos por `emitir_credencial`. Una integración NFC/carnet requiere su propia validación confiable en el servidor.

Respuesta válida:

```json
{ "validation_id": "referencia aleatoria de un solo uso y corta duración" }
```

Vincular `validation_id` al visitante, actor/dispositivo, método y vigencia en el servidor; no devolverlo como un rol firmado por el navegador. Invalidar al usarlo. No usar el UUID público del perfil como credencial.

### POST /access/check

Flujo real:

```json
{ "validation_id": "referencia obtenida en validate", "simulation": false }
```

Respuesta:

```json
{
  "visitor_id": "VIP001",
  "role": "VIP",
  "access": "authorized",
  "destination": "VIP_LOUNGE",
  "robot_target": "robot2",
  "event_type": "vip_handoff",
  "simulation": false,
  "reason": "Membresía y credencial verificadas"
}
```

`access`: `authorized`, `review`, `denied` o `pending`. El frontend exige `simulation` explícito y un destino/robot en resultados autorizados. `visitor_id` es el ID **TEXT de `personas`**, por ejemplo `VIP001`, y no el UUID de Supabase Auth. `auth_user_id` es un UUID opcional reservado a cuentas de miembros y administradores.

Reglas que debe implementar el responsable de FastAPI consultando Supabase al momento de decidir:

| Categoría | Verificar                                                                               | Destino / robot                                                         |
| --------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| VIP       | Rostro + voz enrolada (sin credencial), membresía activa; reserva si corresponde        | Destino permitido VIP; `vip_handoff` a robot2 solo tras autorización    |
| REGULAR   | Rostro + nombre, últimos 4 dígitos del documento y voz; membresía y reserva en ventana  | Servicio reservado, robot1; sin reserva, recepción de miembros          |
| GUEST     | Invitación activa, rango `valid_from`/`valid_until`, anfitrión miembro activo y destino | Solo destino de invitación, robot1                                      |
| STAFF     | Rostro + carné/QR y asignación SHIFT activa dentro del horario del turno                | Solo `authorized_zone`, robot1                                          |
| EXTERNAL  | Rostro + QR de la orden, empresa y EXTERNAL_ORDER activa dentro del horario             | Solo zona de trabajo; jamás zona social, robot1                         |

Si se requiere verificación adicional de identidad, devolver `review`; una consulta fallida, timeout o perfil desconocido nunca implica `authorized`. El backend determina su ventana de llegada para reservas; todos los tiempos de reserva se interpretan en `America/Bogota`, mientras las vigencias son `timestamptz`.

Persistir la decisión en `eventos_acceso` **antes** de comunicarla a los robots. Generar los campos en servidor, consultando identidad y autorizaciones vigentes. Ante carreras entre revocación y acceso, volver a verificar o bloquear registros dentro de una transacción antes de la decisión. Evitar comandos duplicados con un identificador de evento/idempotencia. Ante persistencia fallida, no emitir acceso físico.

Simulación (solo ADMIN, nunca comandos físicos):

```json
{
  "visitor_id": "VIP001",
  "scenario": "VIP",
  "simulation": true,
  "requested_outcome": "authorized"
}
```

`scenario` y `requested_outcome` son únicamente entradas del banco de pruebas, no evidencias de identidad ni permisos. Habilitar estas entradas solo con simulación permitida en el servidor. Respuesta con la misma estructura y `simulation:true`; puede persistirse como tal en `eventos_acceso`. Si el backend aún no implementa este contrato, la UI muestra fallback ficticio DEMO y no lo graba en la base real.

### POST /events

No debe aceptar `access_status:authorized`, rol o destino enviados por un miembro. Para la acción de asistencia, aceptar solamente:

```json
{ "event_type": "assistance_requested" }
```

Resolver el solicitante desde JWT y enviar al equipo/cola existente. Responder `{"accepted":true}` solo después de encolar. Si se registra en `eventos_acceso`, usar `estado_acceso:PENDIENTE`, `simulacion:false`, `robot:robot1`, persona y categoría derivadas en servidor. Otros eventos solo pueden originarse en el backend o robots autenticados y deben validarse según su tipo. El SDK del frontend expone la capa API, pero no envía decisiones de acceso a este endpoint.

### GET /vip/context/{id}

Autenticar ADMIN/robot VIP o el mismo miembro VIP autorizado. Comprobar autorización y handoff vigente en servidor; no basta conocer el ID. Devolver el mínimo contexto necesario:

```json
{
  "visitor_id": "VIP001",
  "message": "Bienvenida a su experiencia exclusiva. Tiene una reserva en la cancha 2 a las 4:00 p. m.",
  "reservation_label": "Cancha 2 · 16:00"
}
```

Para un handoff DEMO, el servidor debe mantener contexto DEMO ligado al actor/evento sin reutilizarlo para el robot físico. Si no devuelve contexto, el frontend no debe inventarlo en el flujo real.

## Supabase como fuente compartida

1. Usar las tablas en español de [nclub_completo.sql](../supabase/nclub_completo.sql): `personas`, `membresias`, `servicios`, `reservas`, `credenciales`, `invitaciones` y `permisos_laborales`. Resolver identidades con `personas.id` (TEXT). No consultar las tablas del esquema anterior en inglés.
2. Mantener las mismas referencias al emitir eventos. Si la integración facial usa identificadores de dispositivo, mapearlos a perfiles en el servidor, nunca duplicar estados de membresía.
3. No mantener una réplica SQLite autoritativa: la revocación o cancelación en la app debe surtir efecto en el siguiente `/access/check`. Si se usa caché, no decidir acceso cuando la fuente compartida no se pueda verificar.
4. El backend escribe `eventos_acceso` con su credencial privada. Realtime entrega eventos únicamente a ADMIN o al titular según RLS. La UI también vuelve a consultar cada 8 segundos.
5. El frontend nunca ve `token_hash` ni credenciales ajenas. Es responsabilidad del backend revalidar todas las reglas de acceso incluso después de verificar un hash válido.

### Correspondencia entre API y base de datos

La API conserva sus campos de respuesta para la interfaz. FastAPI traduce los nombres y categorías al leer y escribir SQL:

| API | Base de datos |
| --- | --- |
| `visitor_id` | `persona_id`, referencia a `personas.id` |
| `role` | `categoria`: VIP/REGULAR sin cambio; GUEST → INVITADO; STAFF → PERSONAL_INTERNO; EXTERNAL → TRABAJADOR_EXTERNO |
| `event_type` | `tipo_evento` |
| `access` / `access_status` | `estado_acceso`: pending → PENDIENTE; authorized → AUTORIZADO; denied → DENEGADO; review → REVISION |
| `destination` | `destino` |
| `robot_target` | `robot` |
| `simulation` | `simulacion` |

Comprobar `personas.activo`, la coincidencia de `membresias.nivel` con `personas.categoria`, `estado='ACTIVA'` y `vigencia_hasta` en cada llegada de miembros. Para reservas: `estado='CONFIRMADA'`, `fecha_inicio`, `fecha_fin` y `servicio_id`. Para invitados: `estado='ACTIVA'`, `valido_desde`, `valido_hasta`, `anfitrion_id` y membresía del anfitrión. Para trabajadores: `estado='ACTIVO'`, tipo, ventana, destino y `requiere_acompanamiento`. Un permiso `CANCELADO`, una invitación `CANCELADA`/`UTILIZADA` o una membresía `SUSPENDIDA` no autorizan ingreso. Una autorización sin anfitrión identificado debe enviarse a revisión, sin asumir identidad a partir de un nombre.

Los destinos se guardan como textos del club, por ejemplo `VIP Lounge`, `Restaurante principal`, `Oficina administrativa` y `Zona técnica`. El backend devuelve un destino de esa misma autorización. Los enums de destino en la tabla anterior describen el contrato conceptual; no deben usarse para ignorar el destino concreto ni conceder zonas adicionales.

## Integración física pendiente

> Actualización: el agente ROS 2/AimDK está en `robot_agent/` y su procedimiento verificado contra la documentación oficial, en [ROBOT.md](ROBOT.md). Sigue pendiente probarlo en el robot físico.

Conectar el SDK/protocolo real de AGIBOT desde FastAPI. El robot1 verifica al visitante; solo una decisión `authorized` VIP puede generar `vip_handoff`. Robot2 recibe contexto mínimo verificado. Una prueba `simulation:true` jamás debe cruzar el adaptador físico. Movimiento, síntesis de voz y callbacks de finalización dependen del hardware del equipo y no están implementados en esta aplicación web.

### Preparar AGIBOT X2 Ultra con Ubuntu

1. Confirma en la placa si es **X2 Ultra** o **X2 Ultra (new version)** y anota la versión de firmware. Descarga AimDK_X2 compatible con ese firmware; no mezcles versiones.
2. Para desarrollar desde un PC Ubuntu, la guía vigente indica Ubuntu 22.04 LTS y ROS 2 Humble para el flujo de host externo. Conecta el puerto Ethernet SDK dedicado del robot al PC, configura el PC como `10.0.1.2/24` y usa el nodo de desarrollo en `10.0.1.41`. Las credenciales SSH las entrega AGIBOT/soporte.
3. Desde AimDK_X2 1.2.0, los programas de desarrollo ejecutados dentro del computador del robot deben compilarse y correr en el contenedor de desarrollo. La alternativa PC/Computing Pack + red entre dispositivos sigue el flujo de SDK cruzado. Sigue la guía para el modo exacto de tu firmware.
4. Primero ejecuta desde los ejemplos AimDK los lectores de cámara/audio y las demos de sensores, sin movimiento. Verifica la API disponible para tu versión y qué cámara/micrófono puedes suscribir. Luego crea un proceso agente en el X2 que tome esos datos y publique eventos al backend FastAPI por una red privada autenticada.
5. FastAPI valida la identidad y permisos con Supabase, guarda el evento y la decisión, y publica solo el stream/transcripción y eventos autorizados al panel ADMIN. Mantén una conexión persistente desde el agente al backend para medios (por ejemplo WebRTC para vídeo/audio interactivo); no envíes vídeo/audio continuo dentro de JSON ni conectes el navegador directamente a ROS/robot.
6. Prueba primero con acceso físico deshabilitado. Habilita movimientos o guía de visitantes solo tras validar hardware, frenos/parada de emergencia, red, latencia y reglas de seguridad junto al integrador AGIBOT.

La topología recomendada es `cámaras/micrófonos X2 → agente AimDK/ROS 2 → FastAPI privado → panel ADMIN`. La app web ya presenta el monitor y requiere implementar `/robot/monitor` y los endpoints privados de stream en el backend. AimDK expone el acceso de desarrollo, pero los nombres concretos de topics, APIs y ejemplos de audio/video dependen de la versión/modelo; confirma esos detalles en el SDK que corresponda al equipo.
