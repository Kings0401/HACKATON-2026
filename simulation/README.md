# Simulación MuJoCo · clasificación en la recepción de N Club

Muestra cómo el AGIBOT X2 Ultra clasifica a quien llega al club, con las cinco
categorías (VIP, Regular, Invitado, Personal interno, Proveedor o trabajador
externo) y además una persona no registrada.

Cada categoría combina el rostro con su propio factor y tiene su propio trato:

| Categoría | Factores |
|---|---|
| Categoría | Factores | Trato del robot |
|---|---|---|
| VIP | Rostro + **voz** registrada. Sin credencial. | Preferencial: la saluda por su nombre, le pregunta qué quiere disfrutar y el AGIBOT 02 la recibe. |
| Regular | Rostro + **nombre completo** + **últimos cuatro dígitos del documento** + **voz**. Sin credencial. | Estricto: no continúa hasta verificar los tres datos, pide lo que falte y al tercer intento fallido deriva a recepción. |
| Invitado | Rostro + **QR de invitación**, con anfitrión de membresía vigente. | Cordial: pide el QR y confirma al anfitrión. |
| Personal interno | Rostro + **carné (QR)**, cruzado con el **horario de su turno**. | Cercano: conversa («¿Cómo va su día?») y le pide amablemente el carné. Le dice hasta qué hora va su turno. |
| Proveedor / trabajador externo | Rostro + **QR de la orden de servicio**. | Formal: le da la bienvenida al área de proveedores, pide la orden y le indica que espere a su acompañante. |

**Todo es simulado.** No se usan cámaras, micrófonos, el robot físico ni
Supabase. El club es el **mapa esquemático demo** (`shared/club-map.json`), no
el plano real.

## Qué es real y qué es simulado

| Parte | En la simulación |
|---|---|
| Robot | Modelo oficial **AGIBOT X2 Ultra** (MJCF `X2_URDF-v1.3.0`, licencia Mulan PSL v2), con las mismas articulaciones y límites. Las mallas visuales están simplificadas para renderizar rápido. |
| Cámara de la frente | Cámara `head_cam` agregada en `head_pitch_link`: 1280×720 y unos 68° de campo de visión. La posición y el FOV son aproximados, no calibrados con el robot. |
| Reconocimiento facial | **Real**. YuNet y SFace de `vision/` analizan el render de esa cámara, con la misma votación de 2 de 3 fotogramas que en el robot. |
| Lectura del QR | **Real**. El `QrReader` de OpenCV lee el QR que el visitante muestra en el teléfono, dentro del render. |
| Agente del robot | **Real**. Es el `ReceptionAgent` de `robot_agent/`, el mismo que corre en el X2. |
| Decisión y ruta | **Reales**. El backend FastAPI (`create_app`) aplica las reglas de acceso y calcula la ruta Dijkstra por zonas. En la escena solo se ve lo que el backend respondió; nada está guionado. |
| Datos | Base demo en memoria (`MemoryRepository`): Valeria Torres, Santiago Ruiz, Camila López, Daniel Moreno y Laura Pérez. |
| Voz | La frase del visitante entra como **texto**, con el mismo endpoint que el STT del robot. Lo que dice el robot sale como **subtítulos**: es la respuesta del backend, sin audio. |
| Verificación de voz (VIP y regular) | **Simulada.** No hay audio ni voces grabadas. Cada persona tiene una huella sintética (`nclub_sim/voice.py`): una toma queda como voz registrada y el robot envía otra toma al hablar. En vez del modelo ECAPA se comparan los espectros de las dos tomas (las de la misma persona dan ~0.99 y las de otra, 0.67 o menos). El HUD lo rotula como «Voz simulada». En modo `--backend` no se envía voz, porque el backend real usaría ECAPA, y la VIP y el regular pasan a revisión. |
| Movimiento | Es **cinemático**. Se fijan las articulaciones del saludo, el giro de cabeza y el paso de los visitantes. No hay un controlador de equilibrio, que en el robot real lo pone AGIBOT. |
| Guion fijo | Solo son guion la frase de bienvenida del AGIBOT 02 en el traspaso VIP y la del acompañante del proveedor. |

## Instalación (una vez)

```powershell
cd simulation
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python download_model.py   # baja el X2 Ultra oficial (~90 MB) y genera la versión liviana
```

Para el reconocimiento facial hacen falta, como en el resto del proyecto, las
fotos de registro en `vision/dataset/registro/<ID>/` y las de prueba en
`vision/dataset/pruebas/<ID>/`. Las de prueba son las caras que llevan los
visitantes de la escena. También hacen falta los modelos ONNX en
`vision/models/`. Nada de esto se versiona.

Sin el dataset la simulación corre igual, pero solo el invitado y la persona
no registrada llegan a su resultado normal. Las demás categorías exigen rostro
y pasan a revisión o se rechazan.

## Uso

```powershell
# Video completo con HUD (build/nclub_clasificacion.mp4, 1280x720 a 24 fps)
.\.venv\Scripts\python run_simulation.py

# Vista previa rápida (848x480 a 15 fps) o solo algunos flujos
.\.venv\Scripts\python run_simulation.py --rapido --solo vip,ext

# Visor interactivo de MuJoCo (se puede mover la cámara)
.\.venv\Scripts\python run_simulation.py --viewer

# En vivo contra el backend: el robot simulado aparece en Admin → Robots
.\.venv\Scripts\python run_simulation.py --backend http://127.0.0.1:8000 --robot-key <ROBOT_API_KEY>
```

Flujos de `--solo`: `vip`, `reg`, `inv`, `emp`, `ext` y `unk` (persona no
registrada).

Para el modo en vivo use el backend con `NCLUB_BACKEND_MODE=memory`, así no se
escriben datos reales. Las sesiones quedan marcadas como simuladas y el robot
se identifica como `robot-mujoco`.

## Qué muestra cada flujo

1. **Llegada.** El visitante camina hasta la recepción y el AGIBOT 01 lo sigue
   con la cabeza.
2. **Rostro.** La cámara de la frente analiza el render. El agente abre la
   sesión, el robot saluda con el gesto 1002 y responde.
3. **Diálogo y segundo factor.**
   - VIP: el robot la saluda por su nombre y le pregunta qué actividad quiere
     hacer. Al responder se verifica su voz y el backend decide.
   - Regular: el robot le pide su nombre completo y los últimos cuatro dígitos
     del documento (`1020304567` en la base demo) y verifica su voz en esa
     misma frase. Después le pregunta la actividad y el backend decide.
   - Invitado, personal y proveedor: dicen su frase y el robot les pide el QR.
4. **Credencial (invitado, personal y proveedor).** El visitante levanta el
   teléfono con el QR, el agente lo lee y el backend decide. Para el personal
   se cruza con su turno y para el proveedor con la orden de trabajo.
5. **Ruta.** La cinta de la ruta aparece con el color de la categoría y el
   visitante la recorre en avance acelerado. El HUD muestra un minimapa.
   - VIP: el AGIBOT 02 lo recibe en la recepción VIP.
   - Proveedor: espera a su acompañante en la recepción de proveedores.
   - Sin registro: se deriva a recepción humana.

## Archivos

- `download_model.py`: descarga el modelo oficial, agrega `head_cam` y genera las mallas livianas.
- `nclub_sim/scene.py`: club, pabellón de recepción, los dos X2 y los visitantes articulados con rostro y teléfono.
- `nclub_sim/animation.py`: caminar, levantar el QR, saludo del X2 y mirada.
- `nclub_sim/director.py`: guion por visitante conectado al agente y al backend reales.
- `nclub_sim/hud.py`: cámara de la frente con detecciones, etapas por categoría, decisión con el factor validado, minimapa y subtítulos.
- `nclub_sim/voice.py`: huella de voz sintética y verificador simulado (solo con el backend en memoria).
- `run_simulation.py`: línea de comandos para video, visor y modo en vivo.
