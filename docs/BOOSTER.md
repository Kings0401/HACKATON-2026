# Reconocimiento facial con la cámara del Booster K1

El agente AGIBOT existente usa ROS 2 y topics AimDK. Para el Booster K1 se añadió un ejecutable alternativo que toma imágenes RGB con BoosterOS y las procesa con el mismo `FaceEngine` YuNet/SFace, lector QR y backend FastAPI. No publica órdenes de movimiento.

BoosterOS documenta `BoosterRobot.subscribe_image()` para recibir imágenes RGB y `list_sensors()` para consultar los IDs de las cámaras. El SDK actual cubre K1/T1/T2, requiere Python 3.10 o posterior y firmware Booster v1.7 o posterior; confirme esos requisitos con el K1 antes de instalarlo. Referencias: [SDK BoosterOS](https://docs.booster.tech/docs/developer-guide/booster-os-python-sdk/sdk-overview/) y [suscripción a imágenes](https://docs.booster.tech/docs/developer-guide/booster-os-python-sdk/booster-robot-client-reference/sensor-subscription-apis/subscribe-image/).

## Preparación en el Booster

Copie el proyecto en `~/nclub` y ejecute en una terminal del robot:

```bash
cd ~/nclub
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "robot_agent[booster]"
python -m pip install -e vision
python -m nclub_vision.models
```

Configure las variables de conexión usando la clave de robot creada en el backend. No guarde la clave dentro del código ni la publique:

```bash
export NCLUB_API_URL="http://IP_DEL_PC:8000"
export NCLUB_ROBOT_KEY="CLAVE_DEL_ROBOT"
export NCLUB_ROBOT_ID="robot1"
export NCLUB_REGISTRO_DIR="$HOME/nclub/dataset/registro"
# Opcional: un ID de cámara mostrado por robot.list_sensors(); vacío usa la cámara predeterminada.
export NCLUB_BOOSTER_CAMERA_ID=""
```

Inicie el reconocimiento:

```bash
PYTHONPATH="$HOME/nclub/robot_agent:$HOME/nclub/vision" \
  "$HOME/nclub/.venv/bin/python" -m nclub_agent.booster_camera
```

En la aplicación, registre las fotos desde **Admin → Personas**. El agente sincroniza la galería privada al arrancar y cuando detecta cambios, procesa los fotogramas de Booster y reporta las coincidencias al mismo flujo de recepción. La decisión final sigue haciéndose en FastAPI con las credenciales y reglas de acceso de cada persona; el rostro identifica al candidato y no concede acceso por sí solo.

## Comprobación

1. Confirme en el log `Booster conectado`, la lista de cámaras y `Reconocimiento facial listo`.
2. En **Admin → Robots**, confirme que el robot y la cámara estén activos.
3. Muestre una persona con foto registrada; revise que el backend reporte el rostro y que la persona presente la credencial que le corresponda.

La integración de Booster debe iniciarse en el computador del robot con el SDK disponible. No se puede verificar el acceso físico ni elegir entre sus cámaras desde este repositorio sin conectarse al equipo real.
