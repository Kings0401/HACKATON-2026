# Programar el AGIBOT X2 Ultra físico — paso a paso

Basado en la documentación oficial AimDK_X2 1.1.0 (<https://x2-aimdk.agibot.com/en/latest/>), consultada el 24-10-2026. **Nada de esto se ha ejecutado en el robot físico.** Cada fase termina en una comprobación: no avance si falla. El agente N Club **no envía comandos de movimiento**.

## Fase 0 · Seguridad y datos del equipo

1. Robot en su soporte o sentado, en zona despejada, con el control remoto y la parada de emergencia a mano. Una persona responsable del robot presente.
2. Anote en la placa de la parte trasera del cuello el modelo: `X2 Ultra` o `X2 Ultra -N` (= X2 Ultra *new version*).
3. Anote la versión de firmware (app Agibot Go o soporte de AGIBOT). **El SDK debe ser de la misma versión que el firmware.** No actualice el firmware: formatea los discos.
4. Pida a AGIBOT/soporte las credenciales SSH del computador de desarrollo. La documentación no las publica.

## Fase 1 · PC host (Ubuntu 22.04 + ROS 2 Humble)

```bash
# ROS 2 Humble (guía oficial de ROS) y herramientas
sudo apt install ros-humble-ros-base python3-colcon-common-extensions python3-opencv
```

1. Conecte un cable Ethernet del PC al **puerto SDK trasero** del robot. No use Wi-Fi para operar: la guía la reserva para depuración.
2. Configure el PC con IP fija `10.0.1.2`, máscara `255.255.255.0`.
3. Compruebe: `ping 10.0.1.41` (computador de desarrollo). **Nunca** compile ni ejecute en `10.0.1.40` (control de movimiento): la guía lo prohíbe.

## Fase 2 · SDK AimDK

1. Descargue el SDK de su versión desde la barra flotante (esquina inferior derecha) de la documentación oficial.
2. Compílelo:
   ```bash
   source /opt/ros/humble/setup.bash
   cd ~/aimdk && colcon build
   source install/local_setup.bash        # en cada terminal nueva
   ```
3. Comprobación sin movimiento:
   ```bash
   ros2 topic list | grep -E "rgbd_head_front|process_audio_output"
   ros2 topic hz /aima/hal/sensor/rgbd_head_front/rgb_image/compressed   # esperado ≈ 30 Hz
   ros2 service list | grep -E "PlayTts|SetAgentProperties"
   ```
   Si un nombre difiere en su firmware, anótelo: lo cambiará en `robot_agent/config/x2_ultra.yaml`.

**Alternativa en el propio robot (contenedor).** Desde AimDK 1.2.0, los programas propios en el computador de desarrollo deben correr en el contenedor oficial. Allí: compruebe los espejos y `/etc/subgid` (sin espacios finales; corrija con `sudo sed -i 's/[[:space:]]*$//' /etc/subgid` y `podman system migrate`), prepare `~/aimdk-image/Dockerfile` y `run.sh` de la guía "Develop in a Container", y ejecute `podman build -t agi/aimdk-dev:dev .`, `./run.sh` y `podman exec -it aimdk-dev bash`. Dentro del contenedor, limpie y compile con `rm -rf ~/aimdk/build ~/aimdk/install ~/aimdk/log` y `colcon build`.

## Fase 3 · Que el robot hable (antes del agente)

1. Prueba oficial: `ros2 run py_examples play_tts "Hola, soy el robot de N Club"`.
2. Si no suena o el sistema integrado responde en su lugar: por defecto el **sistema de interacción integrado ocupa la entrada y la salida de audio**. Cámbielo a modo de desarrollo secundario:
   ```bash
   ros2 service call /aimdk_5Fmsgs/srv/SetAgentPropertiesRequest aimdk_msgs/srv/SetAgentPropertiesRequest \
     "<payload de la guía: propiedad AGENT_PROPERTY_RUN_MODE (2) = 'only_voice'>"
   aima em stop-app agent
   aima em start-app agent
   ```
   Copie el payload exacto de la sección 8.1 de la documentación de su versión. Para volver al modo normal, use la misma llamada con `'normal'` y reinicie el agente.
3. Prueba con el código N Club (después de la Fase 5): `ros2 run nclub_agent nclub_say "Bienvenido a N Club"` debe imprimir `TTS OK`.

## Fase 4 · Backend y datos

1. En el PC host (o en un servidor alcanzable desde `10.0.1.x`):
   ```bash
   cd backend && python3 -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env          # SUPABASE_URL, SUPABASE_SECRET_KEY (rotada), ROBOT_API_KEY nueva
   python -m nclub_vision.models  # descarga los ONNX verificados por SHA-256
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. Ejecute `supabase/recepcion_robot.sql` en Supabase.
3. Registre los rostros desde **Admin → Personas → icono de cámara** (o "Nuevo miembro" con foto). Quedan en el bucket privado `rostros-nclub`.
4. Antes de usar el robot, pruebe todo con la cámara de su portátil en **Admin → Robots → Probar con la cámara del dispositivo**.

## Fase 5 · Agente N Club en ROS 2

```bash
mkdir -p ~/nclub_ws/src && cd ~/nclub_ws/src
ln -s /ruta/HACKATON-2026/robot_agent nclub_agent
pip install -e /ruta/HACKATON-2026/vision httpx
pip install faster-whisper            # transcripción en español offline (opcional: vosk)
cd ~/nclub_ws && source ~/aimdk/install/setup.bash && colcon build --symlink-install
source install/setup.bash
python -m nclub_vision.sync --dest /data/nclub/dataset/registro   # galería desde Storage
export NCLUB_ROBOT_KEY=<ROBOT_API_KEY>
ros2 launch nclub_agent agent.launch.py
```

Comprobaciones, en este orden:

1. El log muestra `Galería facial: [...]`, la cámara, el audio y `Backend conectado`.
2. En `#/admin/robots`: robot en línea, cámara transmitiendo y micrófono escuchando.
3. Una persona registrada frente al robot → "Hola, <nombre>…". Al mostrar su QR, el robot dice la decisión y el panel muestra la ruta.
4. Diga, después de la palabra de activación si el modo la exige, "tengo una reserva": aparece la transcripción en el panel.

Opción con Docker en el PC: `docker build -f robot_agent/docker/Dockerfile -t nclub-agent .` y ejecútelo montando el SDK en `/sdk` (ver `docs/ROBOT.md`).

## Fase 6 · Ajustes con el robot real

- **Cámara**: si los rostros a 1–2 m se ven pequeños, pruebe la estéreo frontal (`stereo_head_front_left/rgb_image/compressed`). Recalibre con fotos de esa cámara: `python -m nclub_vision.calibrate`.
- **Voz**: ajuste `asr_model` (`small` o `medium`) según la CPU; mida la latencia.
- **Red**: agente y backend en la red cableada; HTTPS si el backend está fuera del PC.
- **Movimiento** (guiar físicamente hasta el destino): no implementado. Requiere SLAM/navegación de AimDK, mapa real, pruebas de seguridad y autorización del responsable del robot.

## Problemas frecuentes

| Síntoma | Causa probable | Acción |
| --- | --- | --- |
| `aimdk_msgs no está disponible` | SDK no cargado | `source ~/aimdk/install/setup.bash` antes de lanzar |
| Sin topics desde el PC | Red o versión | Cable al puerto SDK, IP `10.0.1.2/24`, SDK = firmware |
| `TTS no disponible tras 8 intentos` | Servicio ausente o audio ocupado | Fase 3 (modo `only_voice`) |
| Transcripciones vacías | ASR no instalado | `pip install faster-whisper` o `asr_engine: vosk` |
| Siempre "revisión" para VIP | Rostro no registrado o similitud baja | Subir foto desde Admin y recalibrar |
| `401 Robot no autorizado` | Clave distinta | `NCLUB_ROBOT_KEY` = `ROBOT_API_KEY` del backend |
