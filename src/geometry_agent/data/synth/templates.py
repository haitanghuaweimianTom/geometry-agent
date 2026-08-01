"""题型模板 (design/09-Dataset.md §4.2).

Each template defines:
  * ``sample_params(rng) -> dict``  -- randomized but geometrically valid params
  * ``construct(params) -> ConstructedScene`` -- builds a :class:`ConstructSpec`
    and delegates to :class:`GeometryConstructor`

Labels are allocated A, B, C, ... in construction order.

Templates implemented:
  * :class:`TriangleTemplate`         -- triangle_basic
  * :class:`CircleTangentTemplate`    -- circle_tangent
  * :class:`CircleInscribedTemplate`  -- circle_inscribed_angle
  * :class:`EllipseFocusTemplate`     -- ellipse_focus
  * :class:`TwoCirclesTemplate`       -- two_circles
"""
from __future__ import annotations

import math
import random
from typing import Any

from .constructor import (
    ConstructedScene,
    ConstructSpec,
    GeometryConstructor,
    _CircSpec,
    _EllSpec,
    _PolySpec,
    _PtSpec,
    _SegSpec,
)


CANVAS_W = 400
CANVAS_H = 320
PAD = 40


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #
class TemplateBase:
    """Base class: subclasses implement ``sample_params`` and ``_build_spec``."""

    name: str = "base"

    def sample_params(self, rng: random.Random) -> dict[str, Any]:
        raise NotImplementedError

    def _build_spec(self, params: dict[str, Any]) -> ConstructSpec:
        raise NotImplementedError

    def construct(self, params: dict[str, Any]) -> ConstructedScene:
        spec = self._build_spec(params)
        return GeometryConstructor(image_size=spec.image_size).construct(spec)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _label(idx: int) -> str:
    """0->A, 1->B, ... 25->Z, 26->A1, 27->B1 ..."""
    if idx < 26:
        return chr(ord("A") + idx)
    return chr(ord("A") + (idx % 26)) + str(idx // 26)


def _rand_point(rng: random.Random, w: int = CANVAS_W, h: int = CANVAS_H,
                pad: int = PAD) -> tuple[float, float]:
    return float(rng.randint(pad, w - pad)), float(rng.randint(pad, h - pad))


def _triangle_inequality_ok(a: tuple[float, float], b: tuple[float, float],
                             c: tuple[float, float], min_side: float = 25.0) -> bool:
    ab = math.hypot(a[0] - b[0], a[1] - b[1])
    bc = math.hypot(b[0] - c[0], b[1] - c[1])
    ca = math.hypot(c[0] - a[0], c[1] - a[1])
    if min(ab, bc, ca) < min_side:
        return False
    # non-collinear (area > 0)
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(cross) < min_side * min_side:
        return False
    return ab + bc > ca and bc + ca > ab and ca + ab > bc


# --------------------------------------------------------------------------- #
# 1. TriangleTemplate
# --------------------------------------------------------------------------- #
class TriangleTemplate(TemplateBase):
    name = "triangle_basic"

    def sample_params(self, rng: random.Random) -> dict[str, Any]:
        for _ in range(200):
            a = _rand_point(rng)
            b = _rand_point(rng)
            c = _rand_point(rng)
            if _triangle_inequality_ok(a, b, c):
                return {"A": a, "B": b, "C": c}
        # deterministic fallback
        return {"A": (80.0, 80.0), "B": (320.0, 80.0), "C": (200.0, 260.0)}

    def _build_spec(self, params: dict[str, Any]) -> ConstructSpec:
        a, b, c = params["A"], params["B"], params["C"]
        pts = [
            _PtSpec(id="P_A", label="A", coords=(float(a[0]), float(a[1]))),
            _PtSpec(id="P_B", label="B", coords=(float(b[0]), float(b[1]))),
            _PtSpec(id="P_C", label="C", coords=(float(c[0]), float(c[1]))),
        ]
        segs = [
            _SegSpec(id="L_AB", label="AB", p1="P_A", p2="P_B"),
            _SegSpec(id="L_BC", label="BC", p1="P_B", p2="P_C"),
            _SegSpec(id="L_CA", label="CA", p1="P_C", p2="P_A"),
        ]
        polys = [_PolySpec(id="Poly_ABC", label="ABC",
                           vertex_ids=["P_A", "P_B", "P_C"], poly_type="triangle")]
        return ConstructSpec(
            template_name=self.name,
            answer="Triangle ABC",
            points=pts,
            segments=segs,
            polygons=polys,
            params=dict(params),
            problem_text="Triangle ABC.",
        )


# --------------------------------------------------------------------------- #
# 2. CircleTangentTemplate
# --------------------------------------------------------------------------- #
class CircleTangentTemplate(TemplateBase):
    name = "circle_tangent"

    def sample_params(self, rng: random.Random) -> dict[str, Any]:
        w, h, pad = CANVAS_W, CANVAS_H, 60
        for _ in range(200):
            ox, oy = float(rng.randint(pad, w - pad)), float(rng.randint(pad, h - pad))
            r = float(rng.randint(40, 90))
            ang = rng.uniform(0, 2 * math.pi)
            ax = ox + r * math.cos(ang)
            ay = oy + r * math.sin(ang)
            # tangent direction = perpendicular to OA
            tx, ty = -math.sin(ang), math.cos(ang)
            tlen = float(rng.randint(70, 130))
            # pick direction sign so B stays inside canvas
            for sign in (1.0, -1.0):
                bx = ax + sign * tlen * tx
                by = ay + sign * tlen * ty
                if pad - 10 <= bx <= w - pad + 10 and pad - 10 <= by <= h - pad + 10:
                    return {"O": (ox, oy), "r": r, "angle": ang,
                            "A": (ax, ay), "B": (bx, by)}
        return {"O": (200.0, 160.0), "r": 60.0, "angle": 0.0,
                "A": (260.0, 160.0), "B": (260.0, 260.0)}

    def _build_spec(self, params: dict[str, Any]) -> ConstructSpec:
        o = params["O"]
        a = params["A"]
        b = params["B"]
        r = float(params["r"])
        pts = [
            _PtSpec(id="P_O", label="O", coords=(float(o[0]), float(o[1]))),
            _PtSpec(id="P_A", label="A", coords=(float(a[0]), float(a[1]))),
            _PtSpec(id="P_B", label="B", coords=(float(b[0]), float(b[1]))),
        ]
        segs = [
            _SegSpec(id="L_OA", label="OA", p1="P_O", p2="P_A"),
            _SegSpec(id="L_AB", label="AB", p1="P_A", p2="P_B"),
        ]
        circles = [_CircSpec(id="C_O", label="O", center_id="P_O", radius=r)]
        return ConstructSpec(
            template_name=self.name,
            answer="AB is tangent to circle O at A; OA perp AB.",
            points=pts,
            segments=segs,
            circles=circles,
            params=dict(params),
            problem_text="AB is tangent to circle O at A.",
        )


# --------------------------------------------------------------------------- #
# 3. CircleInscribedTemplate
# --------------------------------------------------------------------------- #
class CircleInscribedTemplate(TemplateBase):
    name = "circle_inscribed_angle"

    def sample_params(self, rng: random.Random) -> dict[str, Any]:
        w, h, pad = CANVAS_W, CANVAS_H, 70
        for _ in range(200):
            ox, oy = float(rng.randint(pad, w - pad)), float(rng.randint(pad, h - pad))
            r = float(rng.randint(50, 100))
            if not (pad <= ox - r and ox + r <= w - pad and pad <= oy - r and oy + r <= h - pad):
                continue
            # 3 angles, spread apart
            base = rng.uniform(0, 2 * math.pi)
            spread = rng.uniform(math.pi / 3, 2 * math.pi / 3)
            angs = [base, base + spread, base + 2 * spread + rng.uniform(-0.3, 0.3)]
            pts = [(ox + r * math.cos(a), oy + r * math.sin(a)) for a in angs]
            if _triangle_inequality_ok(*pts, min_side=30):
                return {"O": (ox, oy), "r": r, "angles": angs,
                        "A": pts[0], "B": pts[1], "C": pts[2]}
        return {"O": (200.0, 160.0), "r": 80.0, "angles": [0.0, 2.0, 4.0],
                "A": (280.0, 160.0), "B": (172.0, 230.0), "C": (172.0, 90.0)}

    def _build_spec(self, params: dict[str, Any]) -> ConstructSpec:
        o = params["O"]
        a, b, c = params["A"], params["B"], params["C"]
        r = float(params["r"])
        pts = [
            _PtSpec(id="P_O", label="O", coords=(float(o[0]), float(o[1]))),
            _PtSpec(id="P_A", label="A", coords=(float(a[0]), float(a[1]))),
            _PtSpec(id="P_B", label="B", coords=(float(b[0]), float(b[1]))),
            _PtSpec(id="P_C", label="C", coords=(float(c[0]), float(c[1]))),
        ]
        segs = [
            _SegSpec(id="L_AB", label="AB", p1="P_A", p2="P_B"),
            _SegSpec(id="L_BC", label="BC", p1="P_B", p2="P_C"),
            _SegSpec(id="L_CA", label="CA", p1="P_C", p2="P_A"),
        ]
        circles = [_CircSpec(id="C_O", label="O", center_id="P_O", radius=r)]
        polys = [_PolySpec(id="Poly_ABC", label="ABC",
                           vertex_ids=["P_A", "P_B", "P_C"], poly_type="triangle")]
        return ConstructSpec(
            template_name=self.name,
            answer="Triangle ABC is inscribed in circle O.",
            points=pts,
            segments=segs,
            circles=circles,
            polygons=polys,
            params=dict(params),
            problem_text="Triangle ABC is inscribed in circle O.",
        )


# --------------------------------------------------------------------------- #
# 4. EllipseFocusTemplate
# --------------------------------------------------------------------------- #
class EllipseFocusTemplate(TemplateBase):
    name = "ellipse_focus"

    def sample_params(self, rng: random.Random) -> dict[str, Any]:
        w, h, pad = CANVAS_W, CANVAS_H, 80
        for _ in range(200):
            cx, cy = float(rng.randint(pad, w - pad)), float(rng.randint(pad, h - pad))
            a = float(rng.randint(70, 110))
            b = float(rng.randint(40, max(41, int(a) - 15)))
            rot = rng.uniform(0, math.pi)
            cr, sr = math.cos(rot), math.sin(rot)
            # check ellipse fits in canvas
            corners = [(-a, -b), (a, -b), (-a, b), (a, b)]
            ok = True
            for dx, dy in corners:
                rx = dx * cr - dy * sr
                ry = dx * sr + dy * cr
                if not (pad <= cx + rx <= w - pad and pad <= cy + ry <= h - pad):
                    ok = False
                    break
            if not ok:
                continue
            c_focal = math.sqrt(max(0.0, a * a - b * b))
            f1 = (cx + c_focal * cr, cy + c_focal * sr)
            f2 = (cx - c_focal * cr, cy - c_focal * sr)
            t = rng.uniform(0, 2 * math.pi)
            px = cx + a * math.cos(t) * cr - b * math.sin(t) * sr
            py = cy + a * math.cos(t) * sr + b * math.sin(t) * cr
            return {"center": (cx, cy), "a": a, "b": b, "rotation": rot,
                    "F1": f1, "F2": f2, "P": (px, py), "t": t}
        # deterministic fallback -- compute foci/P analytically from a, b, rot
        cx, cy = 200.0, 160.0
        a, b, rot = 90.0, 55.0, 0.0
        cr, sr = math.cos(rot), math.sin(rot)
        c_focal = math.sqrt(a * a - b * b)
        f1 = (cx + c_focal * cr, cy + c_focal * sr)
        f2 = (cx - c_focal * cr, cy - c_focal * sr)
        t = math.pi / 2
        px = cx + a * math.cos(t) * cr - b * math.sin(t) * sr
        py = cy + a * math.cos(t) * sr + b * math.sin(t) * cr
        return {"center": (cx, cy), "a": a, "b": b, "rotation": rot,
                "F1": f1, "F2": f2, "P": (px, py), "t": t}

    def _build_spec(self, params: dict[str, Any]) -> ConstructSpec:
        ctr = params["center"]
        a, b, rot = float(params["a"]), float(params["b"]), float(params["rotation"])
        f1, f2, p = params["F1"], params["F2"], params["P"]
        pts = [
            _PtSpec(id="P_O", label="O", coords=(float(ctr[0]), float(ctr[1]))),
            _PtSpec(id="P_F1", label="F1", coords=(float(f1[0]), float(f1[1]))),
            _PtSpec(id="P_F2", label="F2", coords=(float(f2[0]), float(f2[1]))),
            _PtSpec(id="P_P", label="P", coords=(float(p[0]), float(p[1]))),
        ]
        ellipses = [_EllSpec(id="E_O", label="O", center_id="P_O",
                             semi_major=a, semi_minor=b, rotation=rot,
                             foci_ids=["P_F1", "P_F2"])]
        pf1 = math.hypot(p[0] - f1[0], p[1] - f1[1])
        pf2 = math.hypot(p[0] - f2[0], p[1] - f2[1])
        answer = f"PF1 + PF2 = {pf1 + pf2:.4f} = 2a = {2 * a:.4f}"
        return ConstructSpec(
            template_name=self.name,
            answer=answer,
            points=pts,
            ellipses=ellipses,
            params=dict(params),
            problem_text="P is a point on the ellipse with foci F1, F2.",
        )


# --------------------------------------------------------------------------- #
# 5. TwoCirclesTemplate
# --------------------------------------------------------------------------- #
class TwoCirclesTemplate(TemplateBase):
    name = "two_circles"

    def sample_params(self, rng: random.Random) -> dict[str, Any]:
        w, h, pad = CANVAS_W, CANVAS_H, 70
        cases = ["external_tangent", "intersect", "separate", "internal_tangent"]
        for _ in range(300):
            case = rng.choice(cases)
            o1 = (float(rng.randint(pad, w - pad)), float(rng.randint(pad, h - pad)))
            r1 = float(rng.randint(40, 70))
            r2 = float(rng.randint(30, 60))
            if case == "internal_tangent":
                if r2 >= r1:
                    r1, r2 = r2, r1
                d = r1 - r2
            elif case == "external_tangent":
                d = r1 + r2
            elif case == "separate":
                d = r1 + r2 + float(rng.randint(15, 40))
            else:  # intersect
                d = abs(r1 - r2) + float(rng.randint(15, max(16, int(r1 + r2 - abs(r1 - r2) - 15))))
                if not (abs(r1 - r2) < d < r1 + r2):
                    continue
            ang = rng.uniform(0, 2 * math.pi)
            o2 = (o1[0] + d * math.cos(ang), o1[1] + d * math.sin(ang))
            if not (pad <= o2[0] <= w - pad and pad <= o2[1] <= h - pad):
                continue
            if not (pad <= o1[0] - r1 and o1[0] + r1 <= w - pad
                    and pad <= o1[1] - r1 and o1[1] + r1 <= h - pad):
                continue
            if not (pad <= o2[0] - r2 and o2[0] + r2 <= w - pad
                    and pad <= o2[1] - r2 and o2[1] + r2 <= h - pad):
                continue
            result: dict[str, Any] = {"O1": o1, "O2": o2, "r1": r1, "r2": r2,
                                      "d": d, "case": case, "angle": ang}
            # intersection / tangent points
            if case == "intersect":
                # 2 intersections
                a_ratio = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
                h_off = math.sqrt(max(0.0, r1 * r1 - a_ratio * a_ratio))
                mx = o1[0] + a_ratio * math.cos(ang)
                my = o1[1] + a_ratio * math.sin(ang)
                px = -math.sin(ang) * h_off
                py = math.cos(ang) * h_off
                result["P"] = (mx + px, my + py)
                result["Q"] = (mx - px, my - py)
            elif case in ("external_tangent", "internal_tangent"):
                # tangent point on line of centers
                if case == "external_tangent":
                    t1 = o1[0] + r1 * math.cos(ang), o1[1] + r1 * math.sin(ang)
                else:
                    t1 = o1[0] + r1 * math.cos(ang), o1[1] + r1 * math.sin(ang)
                result["T"] = t1
            return result
        return {"O1": (140.0, 160.0), "O2": (260.0, 160.0), "r1": 50.0, "r2": 50.0,
                "d": 100.0, "case": "separate", "angle": 0.0}

    def _build_spec(self, params: dict[str, Any]) -> ConstructSpec:
        o1, o2 = params["O1"], params["O2"]
        r1, r2 = float(params["r1"]), float(params["r2"])
        case = params["case"]
        pts = [
            _PtSpec(id="P_O1", label="O1", coords=(float(o1[0]), float(o1[1]))),
            _PtSpec(id="P_O2", label="O2", coords=(float(o2[0]), float(o2[1]))),
        ]
        segs = [_SegSpec(id="L_O1O2", label="O1O2", p1="P_O1", p2="P_O2")]
        circles = [
            _CircSpec(id="C_1", label="O1", center_id="P_O1", radius=r1),
            _CircSpec(id="C_2", label="O2", center_id="P_O2", radius=r2),
        ]
        if case == "intersect":
            p, q = params["P"], params["Q"]
            pts.append(_PtSpec(id="P_P", label="P", coords=(float(p[0]), float(p[1]))))
            pts.append(_PtSpec(id="P_Q", label="Q", coords=(float(q[0]), float(q[1]))))
            answer = "Circles O1 and O2 intersect at P and Q."
        elif case in ("external_tangent", "internal_tangent"):
            t = params["T"]
            pts.append(_PtSpec(id="P_T", label="T", coords=(float(t[0]), float(t[1]))))
            answer = (f"Circles O1 and O2 are {case.replace('_', ' ')} at T."
                      if case == "external_tangent"
                      else "Circle O2 is internally tangent to circle O1 at T.")
        else:
            answer = "Circles O1 and O2 are separate."
        return ConstructSpec(
            template_name=self.name,
            answer=answer,
            points=pts,
            segments=segs,
            circles=circles,
            params=dict(params),
            problem_text=f"Two circles ({case}).",
        )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
TEMPLATES: dict[str, type[TemplateBase]] = {
    TriangleTemplate.name: TriangleTemplate,
    CircleTangentTemplate.name: CircleTangentTemplate,
    CircleInscribedTemplate.name: CircleInscribedTemplate,
    EllipseFocusTemplate.name: EllipseFocusTemplate,
    TwoCirclesTemplate.name: TwoCirclesTemplate,
}
