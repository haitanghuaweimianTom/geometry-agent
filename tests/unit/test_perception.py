"""Unit tests for the perception layer (GeometryParser).

Synthesizes simple geometry images with numpy/cv2 and asserts that the parser
recovers the expected primitives within tolerance.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from geometry_agent.config import ParserConfig
from geometry_agent.perception.orchestrator import GeometryParser
from geometry_agent.types import Circle, Line, Point, PrimitiveSet


def _blank(size: int = 400, bg: int = 0) -> np.ndarray:
    """Blank BGR image (black background by default, white strokes)."""
    img = np.full((size, size, 3), bg, dtype=np.uint8)
    return img


def _draw_triangle(size: int = 400) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Draw a triangle; return (image, vertices, segments)."""
    img = _blank(size)
    A = (100, 320)
    B = (320, 320)
    C = (210, 100)
    pts = [A, B, C]
    segs = [(A, B), (B, C), (C, A)]
    for p1, p2 in segs:
        cv2.line(img, p1, p2, (255, 255, 255), 3, lineType=cv2.LINE_AA)
    for p in pts:
        cv2.circle(img, p, 4, (255, 255, 255), -1, lineType=cv2.LINE_AA)
    return img, np.array(pts, dtype=np.float64), segs


def _draw_circle(size: int = 400, cx: int = 200, cy: int = 200, r: int = 90) -> np.ndarray:
    img = _blank(size)
    cv2.circle(img, (cx, cy), r, (255, 255, 255), 3, lineType=cv2.LINE_AA)
    return img


def _save(img: np.ndarray, tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    cv2.imwrite(str(p), img)
    return p


def test_parser_imports():
    p = GeometryParser(ParserConfig())
    assert p is not None


def test_triangle_detection(tmp_path: Path):
    img, gt_verts, _ = _draw_triangle()
    img_path = _save(img, tmp_path, "triangle.png")

    parser = GeometryParser(ParserConfig())
    ps: PrimitiveSet = parser.parse(img_path, text="triangle ABC")

    assert len(ps.points) >= 3, f"expected >=3 points, got {len(ps.points)}"
    assert len(ps.lines) >= 3, f"expected >=3 lines, got {len(ps.lines)}"

    # each ground-truth vertex should be near some detected point
    for v in gt_verts:
        best = min(
            np.hypot(pt.coords[0] - v[0], pt.coords[1] - v[1])
            for pt in ps.points
        )
        assert best < 8.0, f"vertex {v} not matched (best dist {best:.2f})"

    # each ground-truth edge should be near some detected line
    gt_segs = [(gt_verts[0], gt_verts[1]), (gt_verts[1], gt_verts[2]), (gt_verts[2], gt_verts[0])]
    for p1, p2 in gt_segs:
        gx, gy = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        best = None
        for ln in ps.lines:
            if not ln.endpoints:
                continue
            mx = (ln.endpoints[0][0] + ln.endpoints[1][0]) / 2
            my = (ln.endpoints[0][1] + ln.endpoints[1][1]) / 2
            d = np.hypot(mx - gx, my - gy)
            if best is None or d < best:
                best = d
        assert best is not None and best < 20.0, f"edge midpoint ({gx},{gy}) not matched"


def test_circle_detection(tmp_path: Path):
    gt_cx, gt_cy, gt_r = 200, 200, 90
    img = _draw_circle(cx=gt_cx, cy=gt_cy, r=gt_r)
    img_path = _save(img, tmp_path, "circle.png")

    parser = GeometryParser(ParserConfig())
    ps: PrimitiveSet = parser.parse(img_path, text="circle O")

    assert len(ps.circles) >= 1, f"expected >=1 circle, got {len(ps.circles)}"
    c: Circle = ps.circles[0]
    cx_err = abs(c.center[0] - gt_cx) / gt_r
    cy_err = abs(c.center[1] - gt_cy) / gt_r
    r_err = abs(c.radius - gt_r) / gt_r
    assert cx_err < 0.05, f"cx error {cx_err:.3f} > 5%"
    assert cy_err < 0.05, f"cy error {cy_err:.3f} > 5%"
    assert r_err < 0.05, f"radius error {r_err:.3f} > 5%"


def test_degradation_no_crash_on_blank(tmp_path: Path):
    """Blank image should not crash the parser; should return empty primitives."""
    img = _blank(200)
    img_path = _save(img, tmp_path, "blank.png")
    parser = GeometryParser(ParserConfig())
    ps = parser.parse(img_path, text="")
    assert ps is not None
    # detectors may return a few spurious things but should not crash
    assert isinstance(ps.points, list)
    assert isinstance(ps.lines, list)
    assert isinstance(ps.circles, list)
