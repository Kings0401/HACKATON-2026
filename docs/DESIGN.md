# Sistema de diseño · "Mañana en el campo"

Identidad clara y serena de un club de golf privado con recepción robótica. Superficies luminosas, verde esmeralda solo para la acción, champaña solo para lo VIP. La pieza memorable es **la línea del recorrido**; todo lo demás permanece en calma.

Archivos: tokens en `:root` de `src/styles.css`; componentes base y pantallas prioritarias en `src/theme.css` (se carga al final); mapa de recorrido en la sección "Navegación interior" de `styles.css`.

## Color

| Token                                         | Valor                                         | Uso                                                                                  |
| --------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------ |
| `--bg`                                        | `#f5f7f5`                                     | Fondo general (blanco frío, no crema)                                                |
| `--surface` / `-2` / `-3`                     | `#ffffff` / `#f2f5f3` / `#e8eee9`             | Tarjetas, campos, estados en reposo                                                  |
| `--line` / `--line-strong`                    | `#e1e8e3` / `#cad6ce`                         | Separadores y bordes                                                                 |
| `--text` / `--text-2` / `--muted` / `--faint` | `#13201b` / `#33433b` / `#5f6f67` / `#86948d` | Jerarquía de texto (todos ≥ 4.5:1 sobre blanco salvo `--faint`, solo para metadatos) |
| `--emerald`                                   | `#1b7556`                                     | Acción primaria, navegación activa, recorrido                                        |
| `--signal`                                    | `#12a26e`                                     | Solo estados en vivo (robot conectado, pasos completados)                            |
| `--accent` / `--accent-text`                  | `#b8955a` / `#8a6a32`                         | Solo VIP y destinos (champaña)                                                       |
| `--ok` `--warn` `--danger` `--info`           | `#1f8a57` `#b7791f` `#c2513d` `#2f78b7`       | Autorizado, revisión/acompañamiento, denegado, informativo                           |

**Identidad de los cinco flujos** (punto y borde sutil, nunca grandes fondos): VIP `--cat-vip #a8874a`, Miembro `--cat-regular #1e8a5f`, Invitado `--cat-guest #2f78b7`, Personal `--cat-staff #7a5bc8`, Proveedor `--cat-external #c26a1e`. Se usan en `.badge.role-*` y en los botones de escenario de Recepción.

Texto sobre fotografía: los contenedores `.landing-hero`, `.auth-photo`, `.dashboard-hero`, `.experience-image`, `.service-image`, `.landing-nav` y `.black-card` redefinen los tokens de texto a blanco; no se escriben colores sueltos dentro de ellos.

## Tipografía

- **Fraunces** (serif de eje óptico, peso 380) para títulos, en sentencia y con `text-wrap: balance`.
- **Manrope** para interfaz, datos y etiquetas; cifras tabulares en tablas, indicadores y métricas.
- Escala: h1 `clamp(34px, 4.2vw, 52px)`, h2 `clamp(24px, 2.6vw, 32px)`, h3 21px, cuerpo 15px/1.6, mínimo 11px solo en etiquetas cartográficas.
- Sin etiquetas en mayúsculas sostenidas: `.eyebrow` es una frase corta en español que aporta información; si es decorativa se elimina (`.eyebrow:empty` se oculta).

## Forma y movimiento

- Radios: 10 px (controles), 12 px (botones, campos), 16 px (tarjetas), 22 px (paneles principales).
- Sombra única y suave (`--shadow`); los bordes hacen la mayor parte de la separación.
- Movimiento solo con propósito: el trazo animado del recorrido, el pulso del robot en vivo y la respuesta a acciones (presionar, activar). `prefers-reduced-motion` desactiva animaciones.
- Foco visible en todos los controles: contorno de 2 px `--signal`.

## Pantallas prioritarias

- **Recepción**: AGIBOT 01 en superficie neutra, AGIBOT 02 en champaña; el robot activo se resalta con un anillo. Cada escenario lleva su color de categoría.
- **Mapa de recorrido**: plano claro con zonas tenues, áreas restringidas rayadas en rojo, ruta esmeralda→champaña con brillo, inicio A (esmeralda) y destino B (champaña), giros numerados y QR en panel neutro.
- **Monitor ADMIN**: franja de estado (robot, cámara, micrófono, sesiones), cámara, voz, última atención con validaciones y ruta entregada, historial.
- **Administración**: indicadores en cifras simples sin ceros a la izquierda; accesos en tipografía de interfaz.

## Decisiones registradas

- 24-10-2026: primera propuesta oscura ("Fairway nocturno"); el cliente la rechazó ("ese verde no me gustó"). Se pasó a esta paleta clara reutilizando los mismos tokens semánticos.
- Los 466 colores sueltos de `styles.css`/`responsive.css` se convirtieron a tokens semánticos; cambiar la paleta ahora es editar `:root`.
- La foto del lounge (rascacielos) se reemplazó por un interior de lounge (ver `docs/ASSETS.md`).
