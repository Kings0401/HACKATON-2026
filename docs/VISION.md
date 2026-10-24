# Visión: reconocimiento facial y QR

Código: `vision/nclub_vision/` (reutiliza YuNet + SFace + similitud coseno de `nclub-vision.zip`).

| Módulo | Función |
| --- | --- |
| `face.py` | `FaceEngine`: detección, alineación, registro y identificación sobre fotogramas en memoria; margen entre la 1.ª y la 2.ª identidad; descarta fotografías duplicadas entre personas |
| `qr.py` | `QrReader` (detección múltiple) y clasificación `secure` (`nclub:v1:`), `static` o `demo` |
| `sources.py` | Orígenes intercambiables: `QueueFrameSource` (ROS 2), `ImageFolderSource`, `OpenCVCameraSource` (solo desarrollo) y conversión `rgb8`/JPEG |
| `sync.py` | Sincronización corregida desde FastAPI/Storage |
| `calibrate.py` | Evaluación de umbrales en conjunto cerrado y abierto |
| `models.py` | Descarga verificada por SHA-256 de los ONNX (no se versionan) |

Los scripts originales están en `vision/scripts/` y ahora usan estos módulos. `face_detection.py` (Haar), `camera_test.py` y `test_models.py` se reemplazan por `FaceEngine` y `vision/tests/`. El `.venv` de macOS (Python 3.9) no se reutilizó; instale las dependencias con `pip install -e vision`.

## Causa real de los errores 404 al sincronizar

Diagnóstico contra el bucket privado real `rostros-nclub` (solo lectura):

1. El bucket y las 18 fotografías existen. Varios nombres tienen espacios y paréntesis, por ejemplo `WhatsApp Image 2026-10-24 at 00.23.06 (1).jpeg`.
2. `GET /rostros/{persona}/{archivo}` exigía `^[A-Za-z0-9_.-]{1,100}$`, así que esos nombres devolvían **400**. Antes de añadirse ese endpoint al final de `main.py`, la ruta no existía y FastAPI respondía **404**.
3. Cualquier excepción de Storage se transformaba en 404, lo que ocultaba la causa.
4. En `sincronizar_rostros.py` un solo archivo fallido abortaba el resto de la persona.

Corrección: el backend valida el nombre contra el **listado real del bucket** (rechaza `/`, `..`, archivos ocultos y caracteres de control), distingue 404 (no existe) de 502 (Storage no responde), y el cliente codifica el nombre e informa cada archivo por separado. Verificado contra el Storage real: **18 de 18 descargadas, 0 errores**.

## Calibración

`python -m nclub_vision.calibrate` sobre `dataset/registro` y `dataset/pruebas` (6 fotografías de prueba):

| Umbral | Aciertos | Falsos positivos (registrados) | Visitante no registrado aceptado |
| --- | --- | --- | --- |
| 0.363 (OpenCV) | 6/6 | 0 | **4/6** |
| 0.50 (script original) | 6/6 | 0 | **3/6** |
| 0.60 | 6/6 | 0 | 1/6 |
| **0.62 (nuevo valor por defecto)** | 6/6 | 0 | **0/6** |
| 0.65 | 5/6 | 0 | 0/6 |

Genuinos: mínimo 0.634, media 0.74. El impostor más alto fue 0.603. Ambos umbrales originales aceptaban a desconocidos como personas registradas. El margen es de apenas 0.03, con 6 imágenes generadas, así que **0.62 es provisional**: repita la calibración con fotografías reales de la cámara del robot.

Hallazgos del dataset:

- `registro/REG001/FOTO.png` y `registro/EMP001/FOTO.png` son **la misma imagen** (mismo SHA-256): un miembro estaba registrado también como empleado. El registro descarta ambas automáticamente; corrija la fuente.
- 6 fotografías de WhatsApp no tienen exactamente un rostro detectable a la resolución mínima y se omiten (se informa cada una).
- Bucket: REG001 tiene 5 fotografías allí y 7 localmente; mantenga Storage como la fuente única.

## Reglas de seguridad aplicadas

- El rostro produce un candidato con su similitud; **nunca autoriza solo** ni asigna categoría. FastAPI exige que el rostro coincida con la persona de la credencial (VIP y personal) y vuelve a comprobar el umbral.
- Las plantillas viven en memoria del agente; no se guardan en tablas. A la base solo llega la persona candidata, la similitud y el umbral.
- El dataset y los modelos están en `.gitignore`.
