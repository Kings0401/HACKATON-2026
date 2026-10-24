# Seguridad, secretos y rotación de claves

## Secretos encontrados en las entregas

| Archivo | Contenido | Riesgo | Acción |
| --- | --- | --- | --- |
| `nclub-backend.zip` → `.env` | `SUPABASE_SECRET_KEY` (sb_secret), `ROBOT_API_KEY` | La clave secreta omite RLS: da lectura y escritura total a la base y a Storage | **Rotar ambas** |
| `nclub-vision.zip` → `.env` | `ROBOT_API_KEY`, `NCLUB_API_URL` | Permite actuar como el robot ante FastAPI | Rotar (es la misma clave) |
| `nclub-vision.zip` | `dataset/` y `rostros_nclub.png` con rostros, `.venv` de macOS | Datos biométricos personales | No publicar; conservar solo en Storage privado |
| `.env.example` / `.env.local` | URL y clave **publishable/anon** | Pública por diseño, protegida por RLS | Ninguna |

Ninguno de estos archivos está versionado: los ZIP, `backend/.env`, `vision/dataset/` y los modelos están en `.gitignore`. Si los ZIP se compartieron por chat o correo, trate las claves como expuestas.

## Rotación

Las muestras de voz se guardan en `voces-nclub`, un bucket privado accesible al backend. El audio para verificar al locutor se procesa en memoria; solo se persiste como evidencia con consentimiento adicional y `STORE_EVIDENCE=true`.
El umbral inicial de locutor es `SPEAKER_THRESHOLD=0.25` (coseno); puede calibrarse con grabaciones consentidas de las condiciones reales del club.

1. **Secret key de Supabase**: Dashboard → Project Settings → API Keys → *Secret keys* → crear una nueva → actualizar `backend/.env` → reiniciar FastAPI → **eliminar la clave anterior**. Si se usaba la `service_role` legada (JWT), deshabilite las claves legadas.
2. **ROBOT_API_KEY**: `python -c "import secrets; print(secrets.token_urlsafe(32))"` → actualizar `backend/.env` y la variable `NCLUB_ROBOT_KEY` del agente → reiniciar ambos. Nunca la escriba en YAML, en el frontend ni en Git.
3. **STREAM_SECRET**: si se fija, use otro valor aleatorio. Al rotarlo, los streams abiertos dejan de ser válidos en menos de 2 minutos.
4. Revise en Supabase → Logs (API, Storage) el uso de la clave anterior entre su creación y su eliminación.

## Controles implementados

- **Frontend**: solo la clave publishable; `config.js` rechaza claves `sb_secret_`/`service_role`.
- **Robot → FastAPI**: `X-Robot-Key` comparada en tiempo constante.
- **ADMIN → FastAPI**: JWT de Supabase verificado con `auth.get_user`, más `personas.auth_user_id` con `categoria='ADMIN'` y `activo`. Monitor, evidencias, validación y simulación lo exigen.
- **Stream de cámara**: MJPEG con token HMAC-SHA256 ligado al robot y al ADMIN; caduca en 120 s y la conexión se cierra a los 10 min. Solo existe el último fotograma, en memoria.
- **Base de datos** (`supabase/recepcion_robot.sql`): RLS en todas las tablas nuevas, lectura solo para ADMIN, escritura solo para el servidor y auditoría inmutable (trigger). Probado con PostgreSQL embebido.
- **Realtime**: canal privado `nclub:monitor`; la política en `realtime.messages` admite solo ADMIN activo.
- **Evidencias**: desactivadas por defecto (`STORE_EVIDENCE=false`). Con consentimiento se guardan en el bucket privado `evidencias-recepcion`, con metadatos, SHA-256 y retención; se entregan con URL firmadas de 120 s.
- **Credenciales en registros**: se enmascaran (`NFC-…`, `nclub:v1:…abcd`); el token completo nunca se guarda.
- **Ruta compartida (QR del celular)**: token aleatorio del que solo se guarda el hash. Vence en 30 min, no contiene nombre ni identificador y **no concede permisos**.
- **Persistencia fallida**: si no se puede registrar la decisión en `eventos_acceso`, una autorización se degrada a revisión manual.
- **DEMO** nunca accede a cámaras ni micrófonos; el backend en modo `memory` marca todo como `simulation=true`.
