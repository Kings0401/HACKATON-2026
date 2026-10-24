# N Club World

MVP mobile first de un club privado de golf: membresías, reservas, QR opacos, administración y recepción diferenciada con dos robots AGIBOT. HTML, CSS y JavaScript modular con Vite; sin React.

## Ejecutar

Requiere Node.js 20.19+ (o 22.12+).

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev
```

Abrir la URL que imprime Vite, normalmente **http://127.0.0.1:5173**. En teléfono y computador conectados a la misma red:

```powershell
npm run dev -- --host 0.0.0.0
```

Abrir `http://IP-DEL-COMPUTADOR:5173` desde el teléfono (permitir Vite en la red privada si el firewall lo solicita). La aplicación se adapta desde 320 px; miembros usan navegación inferior y controles táctiles. Para producción, servir con HTTPS.

```powershell
npm test
npm run build
npm run preview
```

## Presentación sin credenciales

1. En la portada, pulsar **Entrar a mi club → Explorar demo**. También: `/#/demo`. Solo miembros VIP, miembros regulares y administradores tienen acceso a la aplicación. Invitados, personal y proveedores se gestionan desde administración y reciben su QR sin iniciar sesión.
2. **Gabriela / VIP**: membresía BLACK, próxima experiencia, reservas, asistencia simulada, beneficios, QR e historial.
3. **Alejandro / Miembro**: reservar golf o restaurante; Lounge VIP permanece bloqueado.
4. **Sofía / Administrador**: consultar las seis categorías, editar nombre/estado, crear invitaciones, turnos y órdenes con QR temporal, revocar permisos y cancelar reservas.
5. Desde la cuenta administradora, abrir **Recepción**, ejecutar **Simular VIP, Miembro, Invitado, Personal, Externo**. Estos son escenarios de ingreso físico al club, no perfiles con acceso a la app. Cada recorrido muestra detección, identificación, vigencia, permisos y resultado. VIP se transfiere a AGIBOT 02. Los demás se atienden con AGIBOT 01 y su destino correspondiente.
6. Cambiar **Resultado de prueba** a revisión o denegación para demostrar excepciones. Suspender un perfil, revocar una invitación u orden y repetir el escenario también demuestra rechazo.
7. Crear una reserva, cambiar de perfil y regresar, o recargar: la persistencia DEMO se conserva.

**DEMO es un entorno separado**: guarda datos ficticios en `localStorage` (`nclub-demo-v1`) y la identidad ficticia de la pestaña en `sessionStorage`. La selección de perfiles existe solamente en DEMO; no inicia sesión en Supabase ni otorga permisos reales. Los QR DEMO tienen prefijo `demo_` y jamás deben aceptarse físicamente. Los eventos DEMO no se escriben en la base real. Para reiniciar, borrar los datos del sitio desde el navegador. Puede deshabilitarse con `VITE_ENABLE_DEMO=false`.

El escenario regular utiliza una **reserva ficticia a la hora de llegada** exclusivamente dentro del evaluador DEMO: permite presentar un recorrido autorizado a cualquier hora sin alterar las reservas persistidas. La reserva VIP «cancha 2 · 16:00» de recepción es contexto ficticio cuando no hay backend. La agenda del miembro conserva sus fechas reales de demostración.

## Conectar Supabase

No hay proyecto ni credenciales incluidos. La integración remota requiere estos pasos y no se considera verificada hasta ejecutarlos contra un proyecto real.

1. Crear un proyecto Supabase.
2. Ejecutar completo [supabase/nclub_completo.sql](supabase/nclub_completo.sql) en SQL Editor. Reutiliza las tablas `personas`, `membresias`, `reservas`, `invitaciones` y `permisos_laborales`, conserva sus datos y agrega catálogo, QR seguros, eventos, RLS y funciones. También funciona en una base nueva. No ejecutar las migraciones anteriores 001/002 para esta instalación.
3. Opcional: ejecutar [supabase/datos_demo.sql](supabase/datos_demo.sql). Carga a Valeria (`VIP001`), Santiago (`REG001`), Camila (`INV001`), Daniel (`EMP001`), Laura (`EXT001`) y `ADMIN001` sin sobrescribir registros ni crear contraseñas. Las reservas y autorizaciones existentes se conservan. Ver [instrucciones y diagnóstico](supabase/README.md).
4. En **Authentication → Users → Add user**, crear las cuentas que se quieran probar (VIP, regular y administrador como mínimo). Usar una contraseña elegida por el equipo. Si se usan correos ficticios, confirmar desde el Dashboard; no esperar mensajes en dominios `.demo`.
5. Para cada cuenta de miembro o administrador, copiar su UUID de Auth y asociarlo al ID de persona mediante [supabase/vincular_cuenta.sql](supabase/vincular_cuenta.sql). Ejecutar como propietario. INVITADO, PERSONAL_INTERNO y TRABAJADOR_EXTERNO no tienen acceso a la app: reciben su QR desde administración sin cuenta de Auth. Incluso una cuenta asociada por error a un visitante queda bloqueada por RLS.
6. Completar `.env.local`:

```dotenv
VITE_SUPABASE_URL=https://TU-PROYECTO.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=TU-CLAVE-PUBLICA
VITE_BACKEND_URL=http://127.0.0.1:8000
VITE_ENABLE_DEMO=true
```

Se acepta `VITE_SUPABASE_ANON_KEY` como alternativa compatible a la publishable key. **Todas las variables VITE son públicas**: jamás colocar `service_role`, secret key o contraseña de base de datos en ellas.

7. Reiniciar Vite. Salir de DEMO e iniciar sesión con **Mi membresía**. La categoría se consulta por `auth_user_id` desde `personas`, y la vigencia desde `membresias`; no se toma de un selector ni de metadata del navegador.
8. Crear/cancelar/modificar una reserva y comprobar `reservas` en Supabase. Abrir otra sesión para verificar sincronización. Generar QR: solo debe aparecer el hash SHA-256 en `credenciales`, nunca el token original. Los códigos estáticos del SQL original son referencias de demostración y no sustituyen estos tokens.
9. Confirmar que Realtime tenga las tablas de la migración en su publicación. Si el proyecto no permite modificar publicaciones, quitar únicamente el bloque de publicación, ejecutar la migración y habilitar las tablas desde el Dashboard. El frontend reconcilia datos cada 8 segundos bajo RLS aunque Realtime no esté disponible.

## Datos y permisos

| Tabla | Lectura desde navegador | Escritura desde navegador |
| --- | --- | --- |
| personas | Miembro: propia; todas para ADMIN activo; sin códigos estáticos | ADMIN: nombre/estado mediante RPC |
| membresias | Propia; todas para ADMIN activo | ADMIN: suspensión mediante RPC; renovar vigencia requiere operación de servidor |
| servicios | Servicios activos | Ninguna |
| reservas | Propias; todas para ADMIN activo | Miembros: propias con validación SQL; ADMIN puede cancelar |
| credenciales | Ninguna | Solo función segura de emisión |
| invitaciones | ADMIN | ADMIN: estado; creación mediante RPC |
| permisos_laborales | ADMIN | ADMIN: estado; creación mediante RPC |
| eventos_acceso | Propios; ADMIN | Solo backend con credencial de servidor |

Un usuario no puede cambiar su categoría, vínculo con Auth ni privilegios VIP. Las restricciones VIP y la vigencia de membresía se validan en un trigger de servidor al reservar. Exclusiones GiST impiden **solapamientos del recurso y del miembro**, incluso en peticiones concurrentes; cancelar libera el horario. Reservas nuevas: bloques de una hora entre 08:00 y 18:00, hasta 90 días y dentro de la vigencia de membresía, zona `America/Bogota`. Cada servicio representa un recurso de capacidad uno. `consultar_disponibilidad` devuelve solo horas ocupadas, sin identidades ajenas. Las reservas anteriores conservan sus ventanas originales y se pueden cancelar; no se ofrece cambiar de horario a registros sin servicio o con duración distinta de una hora.

`emitir_credencial` genera 256 bits aleatorios, revoca la credencial anterior y devuelve el token **una sola vez**. El QR contiene `nclub:v1:TOKEN`, sin datos personales ni categoría. Miembros: hasta una hora, sin superar su membresía. Invitados/personal/externos: hasta 24 horas desde el comienzo de su ventana autorizada (o desde ahora si ya comenzó), sin superar su autorización ni la vigencia del anfitrión. Puede entregarse anticipadamente para una visita futura. FastAPI debe volver a validar turno, invitación, anfitrión, acompañamiento y zona en cada llegada. Un QR futuro no autoriza entrar antes de `valido_desde`. El token queda en memoria/canvas, sin persistencia en el modo real. Cerrar o navegar elimina el QR visible.

## Conectar FastAPI / AGIBOT

Ver [docs/FASTAPI.md](docs/FASTAPI.md): endpoints, JWT, contratos, flujo de verificación, CORS, escritura de eventos, consentimiento facial y cambios para compartir Supabase en vez de mantener una copia SQLite.

Configurar `VITE_BACKEND_URL` y reiniciar Vite. En una sesión ADMIN real:

- **Comprobar backend** realiza `GET /health`.
- **Verificar una credencial** realiza `/validate`, obtiene `validation_id` y solicita `/access/check`. Solo muestra autorización si el backend devuelve una respuesta válida y `simulation:false`.
- Las simulaciones remotas envían `simulation:true`, nunca una orden real. Si FastAPI falla, aparece un aviso y un resultado ficticio **DEMO**, sin escribir decisiones reales en Supabase.
- Los eventos persistidos por FastAPI actualizan recepción y el historial mediante Realtime y la reconciliación periódica.
- La asistencia real necesita que FastAPI acepte el evento no privilegiado `assistance_requested`. Si no responde, se muestra error; nunca se confirma un envío inexistente.

## Recepción robótica integrada

```text
AGIBOT X2 Ultra ─ AimDK/ROS 2 ─▶ robot_agent (cámara + VAD/ASR) ─▶ vision (rostro + QR)
        ─▶ FastAPI backend/ ─▶ Supabase (reglas, registros, Storage privado, Realtime privado)
        ─▶ decisión + ruta ─▶ voz del robot · pantalla · QR al celular ─▶ panel #/admin/robots
```

| Carpeta | Contenido |
| --- | --- |
| `backend/` | FastAPI organizado (rutas, servicios, repositorio); reutiliza `/resolve-access` y `/rostros` del ZIP |
| `vision/` | Reconocimiento facial y QR sobre fotogramas en memoria, sincronización y calibración |
| `robot_agent/` | Paquete ROS 2 Humble `nclub_agent`, núcleo independiente de ROS, voz, simulador y Docker |
| `shared/club-map.json` | Grafo editable del club (**esquemático y simulado**), común al backend y al frontend |
| `supabase/recepcion_robot.sql` | Robots, sesiones, identificación, transcripciones, evidencias, rutas compartidas y auditoría con RLS |

Puesta en marcha completa sin hardware:

```powershell
# 1. Backend con datos ficticios (no toca Supabase; todo queda marcado como simulación)
cd backend; pip install -r requirements.txt
$env:NCLUB_BACKEND_MODE="memory"; $env:ROBOT_API_KEY="clave-simulada-0123456789"
uvicorn app.main:app --port 8000          # imprime un token ADMIN de memoria para probar /robot/monitor
# 2. Visión (modelos verificados por SHA-256) y robot simulado
pip install -e ..\vision; python -m nclub_vision.models
cd ..\robot_agent; $env:NCLUB_ROBOT_KEY="clave-simulada-0123456789"; python -m nclub_agent.sim
# 3. Frontend
npm run dev
```

Con Supabase real: ejecutar `supabase/recepcion_robot.sql` después de `nclub_completo.sql`, completar `backend/.env` (ver `backend/.env.example`) e iniciar FastAPI sin `NCLUB_BACKEND_MODE`. Si las tablas nuevas aún no existen, la recepción funciona y el monitor avisa de "persistencia degradada".

**Mapa interactivo del recorrido (diferencial)**: cuando FastAPI autoriza a alguien (o aprueba su ingreso con acompañamiento), calcula con Dijkstra la ruta desde recepción hasta el destino autorizado, solo por las zonas permitidas para su categoría: VIP por el ala VIP; invitados únicamente por la casa club; personal por los corredores de servicio; proveedores solo por la vía de servicio, con parada de acompañamiento. Recepción, el monitor ADMIN y la página pública `#/ruta` dibujan el recorrido con inicio, destino, giros numerados, puntos de referencia, pasos y tiempo estimado. Un QR temporal (30 min, sin datos personales) abre la misma ruta en el celular y **no concede permisos**. En DEMO la ruta se calcula en el navegador con el mismo grafo, verificado contra la versión Python en 270 combinaciones. Para cargar el plano real, edite nodos, coordenadas, conexiones, zonas y alias de destino en `shared/club-map.json`.

**Sin robot conectado**: en `#/admin/robots`, "Probar con la cámara del dispositivo" convierte este equipo en el robot. La cámara envía fotogramas al backend, que ejecuta el mismo agente: reconocimiento facial con recuadros, lectura del QR, voz (Web Speech: micrófono y voz del navegador), decisión según la membresía y ruta. Solo se activa con un clic; se marca como simulación y no graba. En DEMO necesita el backend en modo memoria y su token (lo imprime uvicorn).

**Fotos para reconocimiento**: en Admin → Personas, "Nuevo miembro" crea un miembro VIP o regular con su membresía, una foto opcional y un QR seguro. El icono de cámara de cada fila sube una foto (exige consentimiento y exactamente un rostro; se recodifica sin metadatos y se guarda en el bucket privado `rostros-nclub`). La foto queda disponible al instante para el reconocimiento; el acceso sigue exigiendo credencial y membresía vigente.

Documentación: [FASTAPI.md](docs/FASTAPI.md) · [ROBOT_PASO_A_PASO.md](docs/ROBOT_PASO_A_PASO.md) (programar el robot físico) · [ROBOT.md](docs/ROBOT.md) (AimDK) · [VISION.md](docs/VISION.md) (calibración y causa de los 404) · [SEGURIDAD.md](docs/SEGURIDAD.md) (rotación de claves) · [VALIDATION.md](docs/VALIDATION.md).

## Estado del MVP

**Ejecutable sin servicios externos:** portada, login, dashboards diferenciados, navegación móvil, siete servicios, reserva/modificación/cancelación con persistencia local DEMO, QR reales escaneables con tokens ficticios, administración de personas/invitaciones/turnos/órdenes, cinco escenarios, revisión/denegación, transferencia VIP y registro DEMO.

**Implementado para servicios reales, requiere configurar y verificar en tu proyecto:** Supabase Auth, perfiles, CRUD autorizado de reservas, administración, emisión QR por RPC, restricciones SQL/RLS, Realtime y polling, llamadas autenticadas a FastAPI y recepción de sus decisiones.

**Implementado y probado con hardware simulado** (falta validarlo en el robot): agente ROS 2/AimDK, reconocimiento facial y QR, voz en español (VAD de AimDK o por energía; ASR faster-whisper/Vosk), sesiones y auditoría, stream privado de cámara, transcripción en vivo y mapa de rutas.

**Simulado o fuera de alcance:** movimiento físico de AGIBOT (el agente no envía comandos de movimiento); TTS físico (desactivado por defecto); plano real del club (el mapa es esquemático); identificación facial dentro del navegador (el navegador no captura biometría); evaluación de acceso cuando no hay FastAPI, recomendaciones VIP curadas (no IA generativa), información ambiental/meteorológica (no se inventa), pagos y notificaciones push. La interfaz de robots es una ilustración conceptual, no una representación técnica certificada del hardware.

El navegador no contiene un motor de autorización real. Los controles visuales son de experiencia; Supabase protege los datos y FastAPI es la autoridad exclusiva de acceso físico.

## Estructura

```text
src/
  main.js           Rutas, interacciones y estados
  pages.js          Vistas semánticas reutilizables
  ui.js             Iconos, tarjetas, diálogos, avisos y QR
  data.js           Auth y operaciones Supabase/DEMO separadas
  schema.js         Adaptación de las tablas en español a la interfaz
  api.js            Contratos y cliente FastAPI con timeout/JWT
  realtime.js       Suscripciones privadas y respaldo cada 8 s
  navigation.js     Mapa de recorrido, Dijkstra DEMO y página pública #/ruta
  clubmap.js        Mapa ilustrativo de miembros (#/map)
  demo.js           Fixtures y escenarios estrictamente simulados
  lib.js            Formato, validaciones y utilidades
  styles.css        Identidad visual
  responsive.css    Diseño para teléfono y adaptación desktop
supabase/           Migración, seed y asociación de cuentas
docs/               Contrato FastAPI y procedimiento de validación
tests/              Pruebas de dominio y permisos de escenarios
public/images/      Fotografías locales para la demostración
```

Fuentes: Cormorant Garamond y Manrope mediante Google Fonts (con fuentes de sistema de respaldo). Iconos Lucide. Fotografías de Unsplash, incluidas localmente para no depender de descargas durante la presentación; identificación de recursos en [docs/ASSETS.md](docs/ASSETS.md). Referencias técnicas: [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security), [Realtime](https://supabase.com/docs/guides/realtime/postgres-changes) y [Auth](https://supabase.com/docs/guides/auth).
