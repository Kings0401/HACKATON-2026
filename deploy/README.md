# Cargar N Club en el AGIBOT X2 (desde Windows)

Todo se ejecuta en **PowerShell**, desde la carpeta del proyecto (`C:\Proyectos\hackaton\HACKATON-2026`). Verificado el 24-10-2026 con el X2 de N Club: el agente se instala, sincroniza las fotos de la app, envía la cámara y su estado al backend.

## Qué se sube

| Al robot (`~/nclub`) | En este PC |
| --- | --- |
| `robot_agent/` (agente ROS 2: cámara, micrófono, voz, gestos opcionales) | `backend/` FastAPI conectado a Supabase |
| `vision/` (rostro + QR) y los modelos ONNX | App web (`npm run dev`) |
| `install.sh`, `start.sh`, `stop.sh`, `status.sh`, `voice_mode.sh`, `camaras.py` | |
| `robot.env` con la clave del robot (permisos 600) | |

Las fotos de reconocimiento **no se copian desde el PC**: el robot consulta cada 5 segundos la versión de la galería (`/robot/gallery`). Si cambia, descarga solo lo nuevo y actualiza esas personas en caliente. Un miembro con foto subida desde *Admin → Personas* queda reconocible en segundos, sin reiniciar; si se borra su foto, sale de la galería.

## Una sola vez

1. Cable al puerto Ethernet SDK trasero. IP fija del PC en el adaptador `Ethernet` (PowerShell **como administrador**):
   ```powershell
   New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 10.0.1.2 -PrefixLength 24
   ```
2. Acceso SSH sin contraseña (pide la contraseña del robot dos veces):
   ```powershell
   ssh agi@10.0.1.41 "mkdir -p .ssh"
   type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh agi@10.0.1.41 "cat >> .ssh/authorized_keys; chmod 700 .ssh; chmod 600 .ssh/authorized_keys; echo LLAVE-INSTALADA"
   ```
   Si SSH dice *UNPROTECTED PRIVATE KEY FILE*:
   ```powershell
   icacls "$env:USERPROFILE\.ssh\id_ed25519" /inheritance:r /grant:r "$($env:USERNAME):F" "SYSTEM:F"
   ```

## Cada vez: un solo comando

Encienda el robot, conecte el cable y ejecute:

```powershell
.\deploy\iniciar_todo.ps1
```

El script hace todo en orden y se detiene con un mensaje claro si algo falla:

1. Revisa el cable y asigna la IP `10.0.1.2` si falta (Windows pide permiso).
2. Abre el backend en una ventana nueva y espera a que responda.
3. Abre la app web en otra ventana (`npm run dev`).
4. Sube el código al robot e inicia el agente con la cámara de la frente.
5. Abre el navegador en **Admin → Robots**.

Si PowerShell bloquea scripts: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

La primera instalación en el robot tarda unos minutos (OpenCV y modelo de voz en español). Las siguientes solo suben el código y reinician.

Para hacerlo por partes (tres ventanas): `.\deploy\iniciar_backend.ps1`, `npm run dev` y `.\deploy\desplegar_robot.ps1`.

## Cámara

El robot usa por defecto la cámara **de la frente** (`-Camara frente`). Al arrancar revisa qué cámaras publica el robot y elige en este orden: la RGB frontal de interacción (si el firmware la publica), la estéreo frontal izquierda y por último la RGB-D. El registro muestra cuál eligió (`status.sh`: «Cámara elegida»).

Con el firmware que tenía el robot el 24-10-2026 no aparecía una cámara de interacción aparte, así que "frente" eligió la **estéreo frontal**. Para confirmar con sus propios ojos cuál es cuál:

```powershell
.\deploy\desplegar_robot.ps1 -ProbarCamaras     # trae una foto de cada cámara a deploy\capturas
.\deploy\desplegar_robot.ps1 -Camara rgbd       # usar otra: frente | estereo | rgbd | trasera | /topic/exacto
.\deploy\desplegar_robot.ps1 -SoloReiniciar -Camara estereo   # cambiar de cámara sin volver a subir
```

Las cámaras de 2048 px se reducen a 1280 px antes de analizar, para que el reconocimiento siga siendo rápido.

Abra la app, inicie sesión con la cuenta ADMIN (*Mi membresía*, no *Explorar demo*) y entre a **Admin → Robots**: robot en línea, cámara en vivo, micrófono, transcripción, decisión y ruta. Sin sesión ADMIN la página muestra al menos si el robot está conectado.

## Opciones

```powershell
.\deploy\iniciar_todo.ps1 -Camara estereo -Gestos   # las mismas opciones sirven en iniciar_todo
.\deploy\desplegar_robot.ps1 -Gestos         # saluda con el brazo y da la mano al VIP autorizado
.\deploy\desplegar_robot.ps1 -SoloReiniciar  # reinicia sin volver a subir
.\deploy\desplegar_robot.ps1 -Reinstalar     # repite la instalación de dependencias
.\deploy\desplegar_robot.ps1 -SinVoz         # sin transcripción (más liviano)
.\deploy\iniciar_backend.ps1 -Memoria        # backend con datos ficticios (simulación)
```

Los gestos solo se envían con el robot de pie (`STAND_DEFAULT`), son de brazo (1002 saludar, 1003 dar la mano) y nunca hacen caminar al robot. Úselos con una persona junto al robot y el control remoto a mano.

## Escuchar sin palabra de activación

Por defecto el sistema de voz del X2 solo entrega audio después de su palabra de activación. Para que el agente escuche siempre (desactiva el asistente integrado del robot):

```powershell
ssh agi@10.0.1.41 "bash ~/nclub/voice_mode.sh only_voice"   # volver: ... voice_mode.sh normal
```

El modo queda guardado y **se aplica al reiniciar el robot**: el asistente integrado corre en el computador de interacción interno (10.0.1.42), no en el de desarrollo, así que `aima em` no puede reiniciarlo desde aquí.

## Control y diagnóstico

```powershell
ssh agi@10.0.1.41 "bash ~/nclub/status.sh"        # estado, fotos registradas y últimas líneas
ssh agi@10.0.1.41 "bash ~/nclub/status.sh 80"     # más líneas del registro
ssh agi@10.0.1.41 "bash ~/nclub/stop.sh"          # detener
ssh agi@10.0.1.41 "bash ~/nclub/start.sh"         # iniciar de nuevo
```

| Síntoma | Qué revisar |
| --- | --- |
| `Sin acceso SSH sin contraseña` | Cable, `Get-NetAdapter -Name Ethernet` en *Up*, IP 10.0.1.2, paso de la llave |
| El backend no responde | Ventana 1 abierta; `curl http://127.0.0.1:8000/health` |
| Robot no aparece en línea | `status.sh`; el robot debe llegar a `http://10.0.1.2:8000/health` |
| No reconoce a alguien | Subir su foto en *Admin → Personas* (icono cámara); el robot la toma en unos segundos |
| No transcribe la voz | Palabra de activación o `voice_mode.sh only_voice` |

## Qué sabe decir el robot

- **Bienvenida por categoría**: VIP (transferencia a AGIBOT 02), miembro (reserva), invitado (anfitrión y áreas de la invitación), personal (zona y carné visible) y proveedor (espera de acompañante en la recepción de proveedores).
- **Indicaciones habladas** al autorizar: distancia, tiempo y los primeros giros del recorrido.
- **Preguntas de orientación**: «¿dónde queda el restaurante?», «¿cómo llego a la cancha 2?», «¿qué espacios tiene el club?». A quien aún no mostró su credencial le describe el lugar y le pide la credencial; a quien ya está autorizado lo guía, pero solo por las zonas de su categoría.
- Las distancias salen del mapa esquemático **simulado** (`shared/club-map.json`); al cargar el plano real se actualizan solas.
