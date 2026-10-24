# Contrato de integración — FastAPI y AGIBOT

FastAPI es la única autoridad de identificación y acceso físico. El navegador presenta resultados; no prueba una identidad enviando un rol. Las simulaciones no emiten comandos físicos.

## Configuración del servidor

- Permitir CORS exclusivamente para los orígenes de Vite usados por el equipo (`http://127.0.0.1:5173`, `http://localhost:5173` y, al probar teléfono, la IP LAN explícita), y el dominio HTTPS final. Métodos GET/POST; cabeceras Authorization y Content-Type.
- Validar `Authorization: Bearer <Supabase access_token>` criptográficamente mediante JWKS del proyecto o `supabase.auth.get_user(token)`. Consultar `personas.auth_user_id` por el `sub` verificado. No confiar en `role`, `visitor_id`, metadata de Auth o `simulation` sin permisos del actor.
- Endpoints de recepción/simulación solo para un ADMIN activo o identidad de robot autenticada por el servidor. El navegador nunca recibe el secreto del robot.
- Usar `SUPABASE_URL` y una credencial de servidor **solo en FastAPI**. Una service_role omite RLS: revalidar explícitamente permisos y campos antes de cualquier operación. No exponer un proxy genérico de escritura ni aceptar decisiones arbitrarias de `/events`.
- Los errores deben usar códigos HTTP adecuados y `{"detail":"mensaje comprensible"}` sin tokens, secretos ni datos de otros miembros.

## Endpoints

### GET /health

Público, sin información sensible. Respuesta: `{"status":"ok","database":"supabase"}`. El cliente usa timeout de 10 segundos.

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
| VIP       | Credencial/identidad y membresía activa; reserva si corresponde                         | Destino permitido VIP; `vip_handoff` a robot2 solo tras autorización    |
| REGULAR   | Membresía activa, credencial y reserva válida en ventana de llegada                     | Servicio reservado, robot1; sin reserva, review según política del club |
| GUEST     | Invitación activa, rango `valid_from`/`valid_until`, anfitrión miembro activo y destino | Solo destino de invitación, robot1                                      |
| STAFF     | Credencial y asignación SHIFT activa dentro del horario                                 | Solo `authorized_zone`, robot1                                          |
| EXTERNAL  | Credencial, empresa y EXTERNAL_ORDER activa dentro del horario                          | Solo zona de trabajo; jamás zona social, robot1                         |

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

Conectar el SDK/protocolo real de AGIBOT desde FastAPI. El robot1 verifica al visitante; solo una decisión `authorized` VIP puede generar `vip_handoff`. Robot2 recibe contexto mínimo verificado. Una prueba `simulation:true` jamás debe cruzar el adaptador físico. Movimiento, síntesis de voz y callbacks de finalización dependen del hardware del equipo y no están implementados en esta aplicación web.
