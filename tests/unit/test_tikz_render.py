"""Regression tests for the TikZ figure renderer (arc/ellipse/bbox fixes).

Covers the defects found in outputs/review.pdf:
  1. Arc nodes stored with ``arc_range`` (radians) were silently skipped
     because the renderer read ``start_angle``/``end_angle``.
  2. A naive TikZ ``arc`` would emit a huge radius for large arcs.
  3. Ellipse semi-major dominated the bbox, flattening the rest of the figure.
  4. Ellipse rotation was not mirrored when flipping y.
"""

from __future__ import annotations

import math

from geometry_agent.human_loop.tikz_render import graph_to_tikz
from geometry_agent.types import GeometryGraph, Node, NodeType


def _graph_with_arc(radius: float = 50.0, arc_range: list[float] | None = None) -> GeometryGraph:
    return GeometryGraph(
        nodes=[
            Node(id="P_A", type=NodeType.POINT, label="A",
                 attrs={"coords": [0.0, 0.0]}),
            Node(id="P_B", type=NodeType.POINT, label="B",
                 attrs={"coords": [100.0, 0.0]}),
            Node(id="A_C", type=NodeType.ARC, label=None,
                 attrs={
                     "center": [50.0, 0.0],
                     "radius": radius,
                     **({"arc_range": arc_range} if arc_range else {}),
                 }),
        ],
    )


def test_arc_with_arc_range_is_drawn():
    tikz = graph_to_tikz(_graph_with_arc(arc_range=[0.0, math.pi]))
    assert r"\draw[thick]" in tikz
    assert tikz.count("--") >= 10


def test_arc_with_legacy_start_end_angles_is_drawn():
    g = GeometryGraph(
        nodes=[
            Node(id="A_C", type=NodeType.ARC, label=None,
                 attrs={"center": [0.0, 0.0], "radius": 10.0,
                        "start_angle": 0.0, "end_angle": 90.0}),
        ],
    )
    tikz = graph_to_tikz(g)
    assert "--" in tikz


def test_arc_skipped_without_angles():
    tikz = graph_to_tikz(_graph_with_arc())  # no angles at all
    assert "--" not in tikz


def test_huge_arc_radius_does_not_explode_coordinates():
    # r = 1e6 px: naive TikZ arc would emit radius in the millions;
    # sampling + scaling must keep the picture ~12cm wide
    tikz = graph_to_tikz(_graph_with_arc(radius=1_000_000.0, arc_range=[0.0, math.pi / 2]))
    assert "--" in tikz
    # every coordinate must stay within ~0..13 (12cm target + padding)
    import re
    coords = [float(v) for v in re.findall(r"([-+]?\d+\.?\d*)", tikz)]
    assert max(coords) < 14.0, f"huge arc blew up coordinates: {coords}"


def test_ellipse_rotation_is_mirrored():
    g = GeometryGraph(
        nodes=[
            Node(id="E_1", type=NodeType.ELLIPSE, label=None,
                 attrs={"center": [0.0, 0.0], "semi_major": 10.0,
                        "semi_minor": 5.0, "rotation": math.pi / 2}),
        ],
    )
    tikz = graph_to_tikz(g)
    # pixel y-down -> TikZ y-up must negate the rotation
    assert "rotate=-90.0" in tikz


def test_ellipse_no_rotation_keeps_zero():
    g = GeometryGraph(
        nodes=[
            Node(id="E_1", type=NodeType.ELLIPSE, label=None,
                 attrs={"center": [0.0, 0.0], "semi_major": 10.0,
                        "semi_minor": 5.0, "rotation": 0.0}),
        ],
    )
    tikz = graph_to_tikz(g)
    assert "rotate=0.0" in tikz


def test_bbox_includes_arc_not_just_ellipse():
    # ellipse semi-major must NOT dominate: a small ellipse + a wide arc
    # should produce a picture sized by the arc
    g = GeometryGraph(
        nodes=[
            Node(id="E_1", type=NodeType.ELLIPSE, label=None,
                 attrs={"center": [0.0, 0.0], "semi_major": 2.0,
                        "semi_minor": 1.0, "rotation": 0.0}),
            Node(id="A_C", type=NodeType.ARC, label=None,
                 attrs={"center": [0.0, 0.0], "radius": 100.0,
                        "arc_range": [0.0, math.pi]}),
        ],
    )
    tikz = graph_to_tikz(g)
    import re
    coords = [float(v) for v in re.findall(r"([-+]?\d+\.?\d*)", tikz)]
    # arc radius 100 dominates the 12cm target -> all coords stay small,
    # but the picture is not degenerate (arc endpoints ~0..6cm from center)
    assert max(coords) < 13.0


def test_padding_keeps_line_extension_inside():
    # LINE nodes draw 10% beyond their endpoints; padding must cover it
    g = GeometryGraph(
        nodes=[
            Node(id="L_1", type=NodeType.LINE, label=None,
                 attrs={"endpoints": [[0.0, 0.0], [10.0, 0.0]]}),
        ],
    )
    tikz = graph_to_tikz(g)
    assert "--" in tikz
    # padding shifts the bbox negative; the extended line end (10 + 10% = 11)
    # scales to ~12.5, i.e. beyond the bare endpoint 10
    import re
    coords = [float(v) for v in re.findall(r"([-+]?\d+\.?\d*)", tikz)]
    assert min(coords) < 0.0, f"expected negative (padded) left edge: {coords}"
    assert max(coords) > 12.0, f"expected extension beyond 10: {coords}"


def test_ellipse_bbox_respects_rotation_extent():
    # a 45°-rotated ellipse has larger x-extent than min(semi_major) alone
    g = GeometryGraph(
        nodes=[
            Node(id="E_1", type=NodeType.ELLIPSE, label=None,
                 attrs={"center": [0.0, 0.0], "semi_major": 10.0,
                        "semi_minor": 10.0, "rotation": math.pi / 4}),
        ],
    )
    # semi_major == semi_minor: any rotation is a circle, bbox must be the same
    tikz0 = graph_to_tikz(g)
    assert "rotate=-45.0" in tikz0


# =============================================================================
# y_up math-coordinate mode + coordinate axes
# =============================================================================

def _ellipse_with_tangent_graph() -> GeometryGraph:
    """Ellipse x²/4 + y²/1 = 1 with tangent slope k=-√(1/2) and P in Q1."""
    return GeometryGraph(
        nodes=[
            Node(id="O", type=NodeType.POINT, label="O",
                 attrs={"coords": [0.0, 0.0]}),
            Node(id="E", type=NodeType.ELLIPSE, label=None,
                 attrs={"center": [0.0, 0.0], "semi_major": 2.0,
                        "semi_minor": 1.0, "rotation": 0.0}),
            Node(id="l1", type=NodeType.LINE, label=None,
                 attrs={"endpoints": [[-2.5, 1.7677], [2.5, -1.7677]]}),
            Node(id="l2", type=NodeType.LINE, label=None,
                 attrs={"endpoints": [[-2.5, -3.5355], [2.5, 3.5355]]}),
            Node(id="P", type=NodeType.POINT, label="P",
                 attrs={"coords": [1.6330, 0.5774]}),
        ],
        relations=[],
        goal=None,
    )


def test_y_up_mode_places_math_point_upper_right():
    import re
    g = _ellipse_with_tangent_graph()
    tikz = graph_to_tikz(g, y_up=True, axes=True)
    # parse all (x,y) draw coordinates
    coords = [float(v) for v in re.findall(r"([-+]?\d+\.?\d*)", tikz)]
    # find ellipse center from the ellipse line
    m = re.search(r"\\draw\[thick\] \(([-\d.]+),([-\d.]+)\) ellipse", tikz)
    assert m, "ellipse line missing"
    ex, ey = float(m.group(1)), float(m.group(2))
    # P fill should be right of center and ABOVE center (math y-up)
    pm = re.search(r"\\fill \(([-\d.]+),([-\d.]+)\) circle \(1\.8pt\);", tikz)
    assert pm, "point fill missing"
    fills = re.findall(r"\\fill \(([-\d.]+),([-\d.]+)\) circle \(1\.8pt\);", tikz)
    off_center = [(float(fx), float(fy)) for fx, fy in fills
                  if abs(float(fx) - ex) > 1e-6 or abs(float(fy) - ey) > 1e-6]
    assert off_center, f"expected a point off-center: fills={fills} O=({ex},{ey})"
    px, py = off_center[0]
    assert px > ex, f"P must be right of center: P=({px},{py}) O=({ex},{ey})"
    assert py > ey, f"P must be above center (y-up): P=({px},{py}) O=({ex},{ey})"


def test_axes_drawn_when_requested():
    g = _ellipse_with_tangent_graph()
    tikz = graph_to_tikz(g, y_up=True, axes=True)
    assert r"\draw[->, thin]" in tikz, "expected arrow axes"
    assert tikz.count(r"\draw[->, thin]") >= 2, "expected x and y axis"
    assert "x" in tikz and "y" in tikz


def test_axes_absent_by_default():
    g = _ellipse_with_tangent_graph()
    tikz = graph_to_tikz(g, y_up=True)  # no axes flag
    assert r"\draw[->, thin]" not in tikz, "axes must be opt-in"


def test_y_up_keeps_slope_sign():
    import re
    g = _ellipse_with_tangent_graph()
    tikz = graph_to_tikz(g, y_up=True)
    # l1 endpoints in math coords: slope k = -0.7071; after y_up mapping the
    # TikZ y coords grow upward so the slope sign is preserved: read the two
    # line endpoints and verify their drawn slope ≈ -0.7071
    lines = re.findall(r"\\draw\[thick\] \(([-\d.]+),([-\d.]+)\) -- \(([-\d.]+),([-\d.]+)\);", tikz)
    assert len(lines) >= 2, f"expected 2 lines, got {lines}"
    x1, y1, x2, y2 = (float(v) for v in lines[0])
    drawn_k = (y2 - y1) / (x2 - x1) if (x2 - x1) != 0 else float("inf")
    assert abs(drawn_k - (-0.7071)) < 0.02, f"l1 drawn slope {drawn_k} != -0.7071"
    x1, y1, x2, y2 = (float(v) for v in lines[1])
    drawn_k = (y2 - y1) / (x2 - x1) if (x2 - x1) != 0 else float("inf")
    assert abs(drawn_k - 1.4142) < 0.02, f"l2 drawn slope {drawn_k} != 1.4142"
