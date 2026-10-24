# Booster K1 (Education) · primeras pruebas

Carpeta del **segundo robot**, el Booster K1. No toca nada del AGIBOT X2
(`robot_agent/`, `deploy/`): el X2 sigue en `10.0.1.41` y el PC conserva su
`10.0.1.2`.

## Red

| Equipo | IP | Notas |
|---|---|---|
| PC, adaptador `Ethernet` | `10.0.1.2` | Para el AGIBOT X2, no cambia. |
| PC, adaptador `Ethernet` | `192.168.10.10` | Se **agrega** para el K1, sin puerta de enlace (internet sigue por el Wi-Fi). |
| Booster K1 | `192.168.10.102` | IP de fábrica por cable, usuario `booster`. Dato de una guía de terceros, sin confirmar todavía en este robot. |

## Primer uso

```powershell
# 1. Una vez, en PowerShell COMO ADMINISTRADOR (agrega 192.168.10.10 sin quitar la del X2):
.\booster_k1\configurar_red.ps1

# 2. En PowerShell normal: instala su llave SSH (pide la contraseña del robot una sola vez)
.\booster_k1\conectar.ps1 -InstalarLlave
#    Si el K1 no responde en 192.168.10.102:  .\booster_k1\conectar.ps1 -Buscar

# 3. Que hable
.\booster_k1\hablar.ps1 -Texto "Hola, soy el robot K1 de N Club"
```

La contraseña de fábrica que publica la guía de terceros es `123456`. Si no
funciona, revísela en el manual del robot.

## Agente de recepción completo (igual que el AGIBOT)

```powershell
.\deploy\iniciar_backend.ps1             # en otra ventana, si no está corriendo
.\booster_k1\desplegar_k1.ps1            # sube, instala (1.ª vez, ~10 min) e inicia
.\booster_k1\desplegar_k1.ps1 -SoloReiniciar
.\booster_k1\desplegar_k1.ps1 -Detener
ssh booster@192.168.10.102 'bash ~/nclub/status_k1.sh'    # estado y registro
```

El agente (`robot_agent/nclub_agent/k1_node.py`) usa el mismo `ReceptionAgent`,
reconocimiento facial YuNet/SFace, lector QR, backend y reglas que el X2. En la
web aparece en **Admin → Robots** como «Booster K1» (`robot1`), con su cámara en
vivo, el micrófono y las decisiones.

| Parte | En el K1 (comprobado el 24-10-2026, firmware 1.8.0.9) |
|---|---|
| Cámara | `/booster_video_stream` (JPEG, ~7 Hz, 544×306, gran angular). Funciona mejor a menos de 1 m. |
| Micrófono | El servicio de audio de Booster lo tiene en exclusiva: se lee con `AudioManager.CreateCaptureStream` (PCM NAEC 16 kHz con cancelación de eco). |
| Escucha | Solo transcribe (faster-whisper `small`, offline) cuando hay una sesión abierta y alguien frente a la cámara en los últimos 15 s. El K1 no tiene palabra de activación, y así la charla de fondo no abre sesiones. |
| Voz | Piper `es_MX-claude-high` (offline, natural) por el parlante USB. Si falta, espeak-ng. La voz nativa LUI de Booster responde 400 en esta unidad. |
| Saludo con la mano | Desactivado. Con `-Gestos`, saluda al abrir sesión **solo si el robot ya está en WALK**: nunca cambia de modo ni camina. |
| Entorno | `~/nclub/.venv` con `--system-site-packages`. No modifica el Python ni el SDK del sistema (`booster_robotics_sdk_python` sigue en 1.5.6). |

## Cómo habla

`booster_k1\robot\hablar_k1.py` corre **dentro del K1**:

1. **SDK oficial `boosteros`** (firmware ≥ v1.7):
   `Speech(robot).synthesize(texto, voice, speed)` genera el audio y
   `robot.audio_manager.play_stream(...)` lo reproduce por el parlante.
   Las voces se listan con `.\booster_k1\hablar.ps1 -Voces`. La documentación
   no dice qué idiomas tienen, así que hay que probar si alguna habla bien
   español.
2. **Respaldo `espeak-ng`** (`-Motor sistema`): voz robótica, sirve para
   comprobar que el parlante funciona.
3. **WAV propio** (`-Wav archivo.wav`): reproduce un audio grabado o generado
   en otro lado (PCM de 16 bits).

`.\booster_k1\hablar.ps1 -Diagnostico` muestra qué de esto hay instalado en el
robot.

Si `boosteros` no está instalado, se instala **en el robot** con
`python3 -m pip install "boosteros[brain]"`. Antes revise la versión de
firmware con `.\booster_k1\conectar.ps1`.

## Seguridad

Estos scripts **solo hablan**: no cambian de modo ni mueven articulaciones. El
K1 arranca en `DAMP`. Para moverlo, la secuencia es `DAMP → PREP → WALK`, con
espacio libre alrededor y alguien con el control remoto a mano.

Referencias: [Booster Docs · Python SDK](https://docs.booster.tech/docs/developer-guide/booster-os-python-sdk/sdk-overview/),
[Speech.synthesize](https://docs.booster.tech/docs/developer-guide/booster-os-python-sdk/vision-and-speech/speech/synthesize/),
[play_stream](https://docs.booster.tech/docs/developer-guide/booster-os-python-sdk/booster-robot-client-reference/audio-manager/play-stream/),
[guía de conexión del K1 (terceros)](https://www.roboticscenter.ai/en/hardware/booster-k1/setup).
