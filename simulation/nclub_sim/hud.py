"""Capa informativa sobre el render: cámara de la frente, etapas, decisión,
minimapa con la ruta y subtítulos. Paleta clara del sistema de diseño."""

from __future__ import annotations

import textwrap
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .director import FrameState

# Segundo factor de cada categoría (se muestra en la tarjeta de decisión).
FACTOR_CHECKS = ("voz", "pregunta de identidad", "invitación", "horario de trabajo", "orden de trabajo")

INK = (29, 42, 36)
MUTED = (96, 108, 102)
PAPER = (251, 250, 246)
LINE = (218, 214, 202)
CATEGORY = {
    "VIP": (168, 135, 74), "REGULAR": (31, 138, 94), "INVITADO": (46, 120, 184),
    "PERSONAL_INTERNO": (122, 92, 199), "TRABAJADOR_EXTERNO": (194, 107, 31), "DESCONOCIDO": (110, 112, 118),
}
CATEGORY_LABEL = {
    "VIP": "VIP", "REGULAR": "Regular", "INVITADO": "Invitado", "PERSONAL_INTERNO": "Personal interno",
    "TRABAJADOR_EXTERNO": "Proveedor externo", "DESCONOCIDO": "Sin registro",
}
DECISION = {
    "AUTORIZADO": ((31, 138, 94), "Autorizado"), "ACOMPANAMIENTO": ((194, 107, 31), "Con acompañamiento"),
    "REVISION": ((184, 134, 11), "Revisión humana"), "DENEGADO": ((178, 58, 52), "Denegado"),
}
FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/System/Library/Fonts")]


def _font(names: list[str], size: int):
    for d in FONT_DIRS:
        for n in names:
            if (d / n).is_file():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default(size)


class Hud:
    def __init__(self, width: int, height: int, club: dict):
        self.w, self.h = width, height
        self.k = width / 1280
        k = self.k
        self.f_title = _font(["seguisb.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "Helvetica.ttc"], int(19 * k))
        self.f_body = _font(["segoeui.ttf", "DejaVuSans.ttf", "Helvetica.ttc"], int(15 * k))
        self.f_small = _font(["segoeui.ttf", "DejaVuSans.ttf", "Helvetica.ttc"], int(12.5 * k))
        self.f_bold = _font(["seguisb.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "Helvetica.ttc"], int(15 * k))
        self.f_big = _font(["seguisb.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "Helvetica.ttc"], int(30 * k))
        self.club = club
        xs = [n["x"] for n in club["nodes"].values()]
        ys = [n["y"] for n in club["nodes"].values()]
        self.bounds = (min(xs), min(ys), max(xs), max(ys))

    # ---------- primitivas ----------

    def _panel(self, d: ImageDraw.ImageDraw, box, alpha=232, radius=14):
        d.rounded_rectangle(box, radius=int(radius * self.k), fill=(*PAPER, alpha), outline=(*LINE, 255), width=1)

    def _s(self, v: float) -> int:
        return int(v * self.k)

    # ---------- composición ----------

    def compose(self, frame_rgb: np.ndarray, st: FrameState) -> np.ndarray:
        base = Image.fromarray(frame_rgb).convert("RGBA")
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        self._header(d, st)
        if st.visitor is not None:
            if st.stage < 4:  # durante el recorrido la cámara del robot ya no aporta
                self._headcam(layer, d, st)
            self._decision(d, st)
            self._stages(d, st)
        if st.decision and st.stage >= 4:
            self._minimap(d, st)
        self._subtitles(d, st)
        if st.banner:
            self._banner(d, st.banner)
        if st.note:
            self._note(d, st.note)
        return np.asarray(Image.alpha_composite(base, layer).convert("RGB"))

    def _header(self, d, st: FrameState):
        s = self._s
        text = "SIMULACIÓN MuJoCo · AGIBOT X2 Ultra (modelo oficial) · mapa esquemático demo"
        tw = d.textlength(text, font=self.f_small)
        self._panel(d, (s(16), s(14), s(16) + tw + s(28), s(42)), radius=13)
        d.ellipse((s(26), s(24), s(34), s(32)), fill=(194, 107, 31, 255))
        d.text((s(40), s(20)), text, font=self.f_small, fill=(*INK, 255))
        if st.timelapse > 1.5:
            label = f"Recorrido acelerado ×{st.timelapse:.0f}"
            tw = d.textlength(label, font=self.f_bold)
            self._panel(d, (s(16), s(50), s(16) + tw + s(24), s(80)), radius=13)
            d.text((s(28), s(55)), label, font=self.f_bold, fill=(*INK, 255))

    def _headcam(self, layer: Image.Image, d, st: FrameState):
        s = self._s
        x0, y0, w = self.w - s(16) - s(400), s(14), s(400)
        h = int(w * 9 / 16)
        self._panel(d, (x0 - s(8), y0 - s(4), x0 + w + s(8), y0 + h + s(54)))
        if st.headcam is not None:
            cam = st.headcam.copy()
            for m in st.matches:
                x, y, bw, bh = m.box
                ok = m.persona_id is not None
                color = (60, 160, 90) if ok else (40, 140, 220)
                cv2.rectangle(cam, (x, y), (x + bw, y + bh), color, 4)
                label = f"{m.persona_id} {m.score:.2f}" if ok else f"{m.reason} {max(m.score, 0):.2f}"
                cv2.putText(cam, label, (x, max(30, y - 12)), cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 3)
            for r in st.readings:
                if r.points is not None:
                    pts = r.points.astype(int).reshape(-1, 2)
                    cv2.polylines(cam, [pts], True, (220, 120, 30), 5)
            small = cv2.resize(cam, (w, h), interpolation=cv2.INTER_AREA)[:, :, ::-1]
            layer.paste(Image.fromarray(small).convert("RGBA"), (x0, y0 + s(2)))
        d.text((x0, y0 + h + s(8)), "Cámara de la frente · AGIBOT 01", font=self.f_bold, fill=(*INK, 255))
        face = next((m for m in st.matches if m.persona_id), None)
        status = []
        if face:
            status.append(f"Rostro {face.persona_id} ({face.score:.2f})")
        elif st.matches:
            status.append("Rostro detectado, sin coincidencia")
        if st.readings:
            status.append(f"QR {st.readings[0].payload}")
        d.text((x0, y0 + h + s(28)), " · ".join(status) or "Analizando con YuNet + SFace y lector QR",
               font=self.f_small, fill=(*MUTED, 255))

    def _stages(self, d, st: FrameState):
        s = self._s
        x, y = s(16), self.h - s(196)
        v = st.visitor
        color = CATEGORY.get(v.category, INK)
        title = f"{st.flow_index}/{st.flow_total} · {v.name}"
        self._panel(d, (x, y, x + s(372), y + s(84)))
        d.text((x + s(14), y + s(10)), title, font=self.f_bold, fill=(*INK, 255))
        cx = x + s(14)
        for i, name in enumerate(st.stages):
            done, now = i < st.stage, i == st.stage
            fill = (*color, 255) if (done or now) else (*LINE, 255)
            d.ellipse((cx, y + s(42), cx + s(14), y + s(56)), fill=fill)
            if now:
                d.ellipse((cx - s(3), y + s(39), cx + s(17), y + s(59)), outline=(*color, 255), width=2)
            d.text((cx - s(4), y + s(60)), name, font=self.f_small, fill=(*(INK if now else MUTED), 255))
            if i < len(st.stages) - 1:
                d.line((cx + s(18), y + s(49), cx + s(66), y + s(49)), fill=(*(color if done else LINE), 255), width=2)
            cx += s(72)

    def _decision(self, d, st: FrameState):
        s = self._s
        v, dec = st.visitor, st.decision
        x0, w = self.w - s(16) - s(400), s(400)
        y0 = s(14) + int(s(400) * 9 / 16) + s(66) if st.stage < 4 else s(14)
        lines = []
        if dec:
            route = dec.get("route") or {}
            lines = [("Destino", dec.get("destination") or route.get("destination_label") or "—")]
            if route.get("distance_m"):
                lines.append(("Ruta", f"{route['distance_m']} m · {route.get('minutes', '?')} min · Dijkstra por zonas"))
            passed = [c for c in dec.get("checks", []) if c.get("ok") and c.get("name") != "persona activa"]
            lines.append(("Validado", " · ".join(c.get("name", "") for c in passed) or "—"))
            factor = next((c for c in passed if c.get("name") in FACTOR_CHECKS), None)
            if factor:
                lines.append((factor["name"].capitalize(), factor.get("detail", "")))
            failed = [c for c in dec.get("checks", []) if not c.get("ok")]
            if failed:
                lines.append(("Pendiente", "; ".join(f"{c.get('name', '')}: {c.get('detail', '')}" for c in failed)[:90]))
            if dec.get("robot_target") == "robot2":
                lines.append(("Traspaso", "AGIBOT 02 · recepción VIP"))
        height = s(70) + s(40) * len(lines) if dec else s(64)
        self._panel(d, (x0 - s(8), y0, x0 + w + s(8), y0 + height))
        cat = (dec or {}).get("category") or (v.category if dec else None)
        if not dec:
            d.text((x0 + s(6), y0 + s(12)), "Clasificación en curso…", font=self.f_bold, fill=(*INK, 255))
            d.text((x0 + s(6), y0 + s(36)), "El backend decide con rostro + el factor de cada categoría",
                   font=self.f_small, fill=(*MUTED, 255))
            return
        color, label = DECISION.get(dec.get("decision"), ((90, 90, 90), dec.get("decision", "—")))
        d.rounded_rectangle((x0 + s(6), y0 + s(12), x0 + s(6) + d.textlength(label, font=self.f_bold) + s(22), y0 + s(38)),
                            radius=s(12), fill=(*color, 255))
        d.text((x0 + s(17), y0 + s(15)), label, font=self.f_bold, fill=(255, 255, 255, 255))
        ccol = CATEGORY.get(cat, INK)
        clabel = CATEGORY_LABEL.get(cat, cat or "—")
        cx = x0 + s(6) + d.textlength(label, font=self.f_bold) + s(36)
        d.ellipse((cx, y0 + s(19), cx + s(12), y0 + s(31)), fill=(*ccol, 255))
        d.text((cx + s(18), y0 + s(15)), clabel, font=self.f_bold, fill=(*ccol, 255))
        y = y0 + s(52)
        for key, value in lines:
            d.text((x0 + s(6), y), key, font=self.f_small, fill=(*MUTED, 255))
            d.text((x0 + s(6), y + s(16)), textwrap.shorten(str(value), 58, placeholder="…"), font=self.f_body,
                   fill=(*INK, 255))
            y += s(40)

    def _minimap(self, d, st: FrameState):
        s = self._s
        size = s(250)
        x0, y0 = s(16), self.h - s(196) - size - s(14)
        self._panel(d, (x0, y0, x0 + size, y0 + size))
        bx0, by0, bx1, by1 = self.bounds
        pad = s(16)
        scale = min((size - 2 * pad) / (bx1 - bx0), (size - 2 * pad) / (by1 - by0))

        def p(x, y):
            return x0 + pad + (x - bx0) * scale, y0 + pad + (y - by0) * scale
        nodes = self.club["nodes"]
        for ea, eb in self.club["edges"]:
            a, b = nodes[ea], nodes[eb]
            d.line((*p(a["x"], a["y"]), *p(b["x"], b["y"])), fill=(*LINE, 255), width=max(1, s(3)))
        route = st.decision.get("route") or {}
        color = CATEGORY.get(st.decision.get("category"), INK)
        pts = [p(x, y) for x, y in route.get("points", [])]
        if len(pts) >= 2:
            d.line(pts, fill=(*color, 255), width=max(2, s(5)), joint="curve")
        for x, y in pts[:1]:
            d.ellipse((x - s(5), y - s(5), x + s(5), y + s(5)), fill=(*INK, 255))
        if pts:
            x, y = pts[-1]
            d.ellipse((x - s(6), y - s(6), x + s(6), y + s(6)), fill=(*color, 255), outline=(255, 255, 255, 255), width=2)
        if st.position is not None:
            start = nodes[self.club["start"]]
            sc = self.club["units"]["scale_m_per_unit"]
            mx, my = start["x"] + st.position[0] / sc, start["y"] - st.position[1] / sc
            x, y = p(mx, my)
            d.ellipse((x - s(7), y - s(7), x + s(7), y + s(7)), fill=(255, 255, 255, 255), outline=(*color, 255), width=3)
        d.text((x0 + s(12), y0 + size - s(24)), "Mapa esquemático (simulado)", font=self.f_small, fill=(*MUTED, 255))

    def _subtitles(self, d, st: FrameState):
        s = self._s
        subs = st.subtitles[-2:]
        if not subs:
            return
        width = s(760)
        x0 = (self.w - width) // 2 - s(60) if self.w > s(1100) else s(16)
        x0 = max(s(360), x0)
        y = self.h - s(24)
        for sub in reversed(subs):
            lines = textwrap.wrap(sub.text, 78)[:3]
            h = s(30) + s(21) * len(lines)
            y -= h
            self._panel(d, (x0, y, x0 + width, y + h - s(6)), alpha=238)
            robot = sub.speaker.startswith("AGIBOT")
            d.text((x0 + s(14), y + s(6)), sub.speaker, font=self.f_bold,
                   fill=(*((31, 110, 160) if robot else INK), 255))
            for i, line in enumerate(lines):
                d.text((x0 + s(14), y + s(27) + s(21) * i), line, font=self.f_body, fill=(*INK, 255))
            y -= s(6)

    def _banner(self, d, text: str):
        s = self._s
        tw = d.textlength(text, font=self.f_big)
        x0 = (self.w - tw) // 2 - s(30)
        y0 = self.h // 2 - s(160)
        self._panel(d, (x0, y0, x0 + tw + s(60), y0 + s(64)), alpha=240, radius=20)
        d.text((x0 + s(30), y0 + s(12)), text, font=self.f_big, fill=(*INK, 255))

    def _note(self, d, text: str):
        s = self._s
        tw = d.textlength(text, font=self.f_title)
        x0 = (self.w - tw) // 2 - s(22)
        y0 = s(96)
        self._panel(d, (x0, y0, x0 + tw + s(44), y0 + s(42)), alpha=240)
        d.text((x0 + s(22), y0 + s(9)), text, font=self.f_title, fill=(*INK, 255))
