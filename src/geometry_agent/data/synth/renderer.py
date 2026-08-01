"""Renderer: ConstructedScene -> PNG-style image array (design/09 §4.5).

Uses numpy + OpenCV only (matplotlib-free). Draws:
  * segments / lines / rays as anti-aliased polylines
  * circles as anti-aliased outlines
  * ellipses via :c:func:`cv2.ellipse`
  * points as filled dots with letter labels via :c:func:`cv2.putText`

Coordinate convention: geometry coords are in image-pixel space with the y-axis
pointing **down** (same as OpenCV). Templates generate coords already in this
space, so no flip is needed.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .constructor import ConstructedScene

DEFAULT_STYLE: dict[str, Any] = {
    "image_size": (400, 320),
    "bg_color": (255, 255, 255),
    "line_color": (0, 0, 0),
    "line_width": 2,
    "point_radius": 4,
    "point_color": (0, 0, 0),
    "font_scale": 0.6,
    "font_thickness": 1,
    "font_face": cv2.FONT_HERSHEY_SIMPLEX,
    "label_offset": (6, -6),
}


def _merge_style(style: dict[str, Any] | None) -> dict[str, Any]:
    s = dict(DEFAULT_STYLE)
    if style:
        s.update(style)
    return s


def render(scene: ConstructedScene, style: dict[str, Any] | None = None) -> np.ndarray:
    """Render ``scene`` to an ``H x W x 3`` uint8 BGR array (white background)."""
    s = _merge_style(style)
    w, h = s["image_size"]
    img = np.full((h, w, 3), s["bg_color"], dtype=np.uint8)
    line_color = tuple(s["line_color"])
    point_color = tuple(s["point_color"])
    line_width = int(s["line_width"])
    point_radius = int(s["point_radius"])

    prim = scene.primitives

    # ----- segments / lines / rays -----
    for L in prim.lines:
        if not L.endpoints or len(L.endpoints) < 2:
            continue
        (x1, y1), (x2, y2) = L.endpoints
        # extend infinite lines a bit beyond endpoints for visibility
        if L.type.value == "line":
            dx, dy = x2 - x1, y2 - y1
            n = math.hypot(dx, dy) or 1.0
            dx, dy = dx / n, dy / n
            ext = max(w, h)
            x1, y1 = x1 - dx * ext, y1 - dy * ext
            x2, y2 = x2 + dx * ext, y2 + dy * ext
        elif L.type.value == "ray":
            dx, dy = x2 - x1, y2 - y1
            n = math.hypot(dx, dy) or 1.0
            dx, dy = dx / n, dy / n
            ext = max(w, h)
            x2, y2 = x2 + dx * ext, y2 + dy * ext
        cv2.line(img, (int(x1), int(y1)), (int(x2), int(y2)),
                 line_color, line_width, cv2.LINE_AA)

    # ----- circles -----
    for c in prim.circles:
        r = max(1, int(round(c.radius)))
        cv2.circle(img, (int(round(c.center[0])), int(round(c.center[1]))),
                   r, line_color, line_width, cv2.LINE_AA)

    # ----- ellipses -----
    for e in prim.ellipses:
        cv2.ellipse(
            img,
            (int(round(e.center[0])), int(round(e.center[1]))),
            (max(1, int(round(e.semi_major))), max(1, int(round(e.semi_minor)))),
            float(math.degrees(e.rotation)),
            0, 360, line_color, line_width, cv2.LINE_AA,
        )

    # ----- polygons (light outline already drawn via segments) -----
    for poly in prim.polygons:
        if len(poly.vertices) >= 2:
            pts = np.array([[int(v[0]), int(v[1])] for v in poly.vertices], dtype=np.int32)
            cv2.polylines(img, [pts], isClosed=True, color=line_color,
                          thickness=line_width, lineType=cv2.LINE_AA)

    # ----- points + labels -----
    offx, offy = s["label_offset"]
    for p in prim.points:
        cx, cy = int(round(p.coords[0])), int(round(p.coords[1]))
        cv2.circle(img, (cx, cy), point_radius, point_color, -1, cv2.LINE_AA)
        if p.label:
            cv2.putText(img, p.label, (cx + offx, cy + offy),
                        s["font_face"], s["font_scale"], point_color,
                        s["font_thickness"], cv2.LINE_AA)
    return img


def render_to_file(scene: ConstructedScene, path: str | Path,
                   style: dict[str, Any] | None = None) -> str:
    """Render ``scene`` and write it to ``path`` as PNG. Returns the path."""
    img = render(scene, style=style)
    path = str(path)
    ok = cv2.imwrite(path, img)
    if not ok:
        raise OSError(f"Failed to write image to {path}")
    return path
