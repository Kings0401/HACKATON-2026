# Agente AGIBOT X2 Ultra (AimDK / ROS 2)

Estado: **implementado y probado con hardware simulado. No probado en el robot físico.** Ningún topic, servicio ni dispositivo se ha comprobado físicamente; todo lo siguiente proviene de la documentación oficial y debe confirmarse en el equipo.

## Lo que dice la documentación oficial (consultada el 24-10-2026)

Fuente: <https://x2-aimdk.agibot.com/en/latest/>. La versión publicada es **AimDK_X2 1.1.0**, que cubre X2 Ultra Edition, X2 EDU y X2 Ultra (new version).

| Tema | Dato documentado |
| --- | --- |
| Host de desarrollo | Ubuntu 22.04 LTS, ROS 2 Humble, Python ≥ 3.8, OpenCV, cv_bridge |
| Red cableada X2 Ultra | PC host `10.0.1.2/24`; computador de desarrollo `10.0.1.41`. Wi-Fi (AP) solo para depuración, salto `192.168.88.88` |
| Prohibido | Compilar o ejecutar en el computador de control de movimiento (PC1, `10.0.1.40`) |
| Versiones | **El SDK debe coincidir con el firmware.** Actualizar o bajar firmware formatea discos |
| Contenedor | Desde AimDK 1.2.0 los programas secundarios en el robot deben ejecutarse en el contenedor de desarrollo; en 1.1.0 coexisten ambos modos. El modo PC host no requiere contenedor |
| Cámara usada | `/aima/hal/sensor/rgbd_head_front/rgb_image/compressed`, `sensor_msgs/CompressedImage`, MJPEG 1280×720, 30 Hz |
| Otras cámaras | Estéreo frontal (`stereo_head_front_left/right`, 10 Hz) y trasera (`rgb_head_rear`, rotada 90° en la new version). La cámara de interacción frontal no tiene topics documentados en la página consultada |
| Audio | `/agent/process_audio_output`, `aimdk_msgs/ProcessedAudioOutput`: PCM 16 kHz, 16 bits, mono, con VAD (`BEGIN=1`, `PROCESSING=2`, `END=3`), QoS BEST_EFFORT. En modo por defecto requiere palabra de activación |
| Audio crudo | `/aima/hal/audio/capture` (6 canales: 4 micrófonos + 2 de referencia) |
| TTS | Servicio `/aimdk_5Fmsgs/srv/PlayTts` (`aimdk_msgs/srv/PlayTts`), campos `tts_req.text`, `domain`, `is_interrupted` y `priority_level` |

## Arquitectura del agente

```
X2: cámara RGB-D ──CompressedImage──▶ ros_node.py ─▶ QueueFrameSource ─▶ ReceptionAgent (core.py)
X2: VAD AimDK ──ProcessedAudioOutput─▶ AimdkVadAssembler ─▶ ASR (faster-whisper/Vosk) ─┘   │
                                                                                          ▼
                       FaceEngine + QrReader (vision/) ──▶ BackendClient ──HTTPS + X-Robot-Key──▶ FastAPI
                                                                ◀── decisión, voz, ruta ──┘
                                     PlayTts (opcional, desactivado por defecto)
```

- `core.py` no depende de ROS: lo usan el nodo, el simulador y las pruebas.
- Un fotograma solo se envía al backend como JPEG de vista previa (5 fps como máximo), y solo en memoria. No se graba video.
- El agente **no publica comandos de movimiento** ni modifica el firmware.
- Reconexión: el cliente reintenta con espera exponencial, envía latidos cada 5 s (hasta 30 s sin conexión) y `respawn` en el launch reinicia el proceso. Sin backend, el robot dice "tengo un problema de conexión; recepción le atenderá".

## Puesta en marcha (modo PC host)

1. Anote en la placa del robot el **modelo exacto** (X2 Ultra o X2 Ultra new version) y la **versión de firmware**. Descargue el AimDK_X2 de esa misma versión.
2. Conecte el PC al puerto Ethernet SDK y configure `10.0.1.2/24`.
3. Compruebe los topics **sin movimiento**:
   ```bash
   source /opt/ros/humble/setup.bash && source <aimdk>/install/setup.bash
   ros2 topic list | grep -E "rgbd_head_front|process_audio_output"
   ros2 topic info -v /aima/hal/sensor/rgbd_head_front/rgb_image/compressed
   ros2 topic hz /aima/hal/sensor/rgbd_head_front/rgb_image/compressed
   ros2 service list | grep PlayTts
   ```
   Si un nombre difiere, cámbielo en `robot_agent/config/x2_ultra.yaml`.
4. Copie la galería autorizada (`vision/dataset/registro`, sincronizada con `python -m nclub_vision.sync`) y los modelos (`python -m nclub_vision.models`).
5. Contenedor (recomendado):
   ```bash
   docker build -f robot_agent/docker/Dockerfile -t nclub-agent .
   docker run --rm -it --network host \
     -v /ruta/AimDK_X2:/sdk:ro -v /ruta/dataset:/data/nclub/dataset:ro \
     -e NCLUB_ROBOT_KEY=<ROBOT_API_KEY> -e NCLUB_FIRMWARE=<versión> -e NCLUB_AIMDK_VERSION=<versión> \
     nclub-agent
   ```
   El Dockerfile no se ha construido en este equipo porque Docker Desktop estaba detenido.
6. Habilite `tts_enabled: true` solo con autorización del responsable del robot.
7. En `#/admin/robots` deben aparecer: robot en línea, cámara transmitiendo y micrófono escuchando.

## Simulación (sin hardware)

```powershell
# Terminal 1: backend con datos ficticios (no toca Supabase)
cd backend; $env:NCLUB_BACKEND_MODE="memory"; $env:ROBOT_API_KEY="clave-simulada-0123456789"; uvicorn app.main:app --port 8000
# Terminal 2: cinco visitantes simulados
cd robot_agent; $env:NCLUB_ROBOT_KEY="clave-simulada-0123456789"; python -m nclub_agent.sim
```

El simulador usa imágenes de `vision/dataset/pruebas`, genera los QR y envía frases de texto en lugar de audio. No abre cámaras ni micrófonos.

## Pendiente con el robot físico

- Verificar los topics, el QoS y la latencia reales, y elegir la cámara más adecuada para el rostro a 1–2 m.
- Deshabilitar el sistema de interacción integrado si su VAD/TTS compite con el agente (sección 8.1 de AimDK).
- Medir la precisión facial con fotografías tomadas por la cámara del robot y recalibrar (`docs/VISION.md`).
- Confirmar si el firmware es ≥ 1.2.0, que obliga a usar el contenedor de desarrollo en el computador del robot.
