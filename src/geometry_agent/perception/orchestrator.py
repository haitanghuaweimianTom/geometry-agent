"""GeometryParser: perception-layer orchestrator (design/01 §3, §5, §8).

Wires Preprocessor -> DetectorOrchestrator (point/line/circle/ellipse, with a
second point pass for analytic intersections) -> PrimitiveMerger (consistency)
-> MarkDetector -> Labeler -> PrimitiveSet.

Degradation principle: any failing detector returns [] + a warning; parse() never
raises for detector-level errors (only for unreadable images).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ..config import ParserConfig
from ..logging_util import info, log_step
from ..types import (
    Circle,
    Ellipse,
    Line,
    Mark,
    MetaData,
    Point,
    PrimitiveSet,
)
from .detectors.circle_detector import CircleDetector
from .detectors.ellipse_detector import EllipseDetector
from .detectors.line_detector import LineDetector
from .detectors.mark_detector import MarkDetector
from .detectors.point_detector import PointDetector
from .labeling import Labeler
from .preprocess import Preprocessor, load_image_rgb

SNAP_DIST_PX = 3.0


class DetectorOrchestrator:
    """Runs the four primitive detectors in parallel and aggregates results."""

    def __init__(self, config: ParserConfig):
        self.config = config
        self.point_detector = PointDetector(config)
        self.line_detector = LineDetector(config)
        self.circle_detector = CircleDetector(config)
        self.ellipse_detector = EllipseDetector(config)

    def run(self, gray, binary_clean, skeleton) -> tuple[list[Point], list[Line], list[Circle], list[Ellipse], list[str]]:
        warnings: list[str] = []
        points: list[Point] = []
        lines: list[Line] = []
        circles: list[Circle] = []
        ellipses: list[Ellipse] = []

        # First pass: lines, circles, ellipses in parallel; points initial pass
        def run_lines():
            try:
                return self.line_detector.detect(binary_clean, points=None)
            except Exception as e:
                warnings.append(f"line_detector_failed:{e!r}")
                return []

        def run_circles():
            try:
                return self.circle_detector.detect(binary_clean)
            except Exception as e:
                warnings.append(f"circle_detector_failed:{e!r}")
                return []

        def run_ellipses():
            try:
                return self.ellipse_detector.detect(binary_clean)
            except Exception as e:
                warnings.append(f"ellipse_detector_failed:{e!r}")
                return []

        def run_points_initial():
            try:
                return self.point_detector.detect(gray, binary_clean, skeleton, lines=[], circles=[])
            except Exception as e:
                warnings.append(f"point_detector_initial_failed:{e!r}")
                return []

        with ThreadPoolExecutor(max_workers=4) as ex:
            f_lines = ex.submit(run_lines)
            f_circles = ex.submit(run_circles)
            f_ellipses = ex.submit(run_ellipses)
            f_points = ex.submit(run_points_initial)
            lines = f_lines.result()
            circles = f_circles.result()
            ellipses = f_ellipses.result()
            points = f_points.result()

        # Second pass: re-run point detection with lines/circles to补全 intersections
        try:
            with log_step("perception.orchestrator", "point_pass2", lines=len(lines), circles=len(circles)):
                points2 = self.point_detector.detect(
                    gray, binary_clean, skeleton, lines=lines, circles=circles
                )
            points = PrimitiveMerger.merge_points(points + points2, SNAP_DIST_PX)
        except Exception as e:
            warnings.append(f"point_pass2_failed:{e!r}")

        return points, lines, circles, ellipses, warnings


class PrimitiveMerger:
    """Cross-primitive consistency: dedup points, snap line endpoints, drop circles
    better explained as ellipses (and vice versa)."""

    @staticmethod
    def merge_points(points: list[Point], tol: float = SNAP_DIST_PX) -> list[Point]:
        if not points:
            return []
        kept: list[Point] = []
        for p in points:
            merged = False
            for q in kept:
                if np.hypot(p.coords[0] - q.coords[0], p.coords[1] - q.coords[1]) < tol:
                    # keep the higher-confidence one, preserve label
                    if (p.confidence > q.confidence):
                        q.coords = p.coords
                        q.confidence = p.confidence
                    if q.label is None and p.label is not None:
                        q.label = p.label
                    merged = True
                    break
            if not merged:
                kept.append(p)
        # re-number ids
        for i, p in enumerate(kept):
            p.id = f"P_{i:03d}"
        return kept

    @staticmethod
    def snap_line_endpoints(lines: list[Line], points: list[Point], tol: float = 5.0) -> None:
        for ln in lines:
            if not ln.endpoints:
                continue
            new_eps = []
            for ep in ln.endpoints:
                best = None
                best_d = tol
                for p in points:
                    d = float(np.hypot(p.coords[0] - ep[0], p.coords[1] - ep[1]))
                    if d < best_d:
                        best_d = d
                        best = p.coords
                new_eps.append(best if best is not None else ep)
            ln.endpoints = new_eps
            if len(new_eps) == 2:
                ln.length = float(np.hypot(new_eps[1][0] - new_eps[0][0],
                                           new_eps[1][1] - new_eps[0][1]))

    @staticmethod
    def resolve_circle_ellipse(circles: list[Circle], ellipses: list[Ellipse]) -> tuple[list[Circle], list[Ellipse]]:
        """Drop ellipses that coincide with a circle (same center & ~circle ratio)."""
        kept_e: list[Ellipse] = []
        for e in ellipses:
            dup = False
            for c in circles:
                if (np.hypot(e.center[0] - c.center[0], e.center[1] - c.center[1]) < 4.0
                        and abs(e.semi_major - c.radius) < 4.0):
                    dup = True
                    break
            if not dup:
                kept_e.append(e)
        return circles, kept_e


class GeometryParser:
    """Public entry point: parse(image_path, text) -> PrimitiveSet."""

    def __init__(self, config: ParserConfig):
        self.config = config
        self.preprocessor = Preprocessor(config)
        self.orchestrator = DetectorOrchestrator(config)
        self.mark_detector = MarkDetector(config)
        self.labeler = Labeler(config)

    def parse(self, image_path: Path | str, text: str = "") -> PrimitiveSet:
        warnings: list[str] = []

        with log_step("perception.parser", "load", path=str(image_path)):
            bgr = load_image_rgb(image_path)

        with log_step("perception.parser", "preprocess"):
            pre = self.preprocessor.run(bgr)
        warnings.extend(pre.warnings)

        with log_step("perception.parser", "detect"):
            points, lines, circles, ellipses, det_warnings = self.orchestrator.run(
                pre.gray, pre.binary_clean, pre.skeleton
            )
        warnings.extend(det_warnings)

        # consistency / merge
        with log_step("perception.parser", "merge"):
            points = PrimitiveMerger.merge_points(points, SNAP_DIST_PX)
            PrimitiveMerger.snap_line_endpoints(lines, points)
            circles, ellipses = PrimitiveMerger.resolve_circle_ellipse(circles, ellipses)

        # marks (on raw binary, not text-cleaned, to keep small symbols)
        with log_step("perception.parser", "marks"):
            try:
                marks: list[Mark] = self.mark_detector.detect(
                    bgr, pre.binary, lines=lines, points=points
                )
            except Exception as e:
                warnings.append(f"mark_detector_failed:{e!r}")
                marks = []

        primitive_set = PrimitiveSet(
            points=points,
            lines=lines,
            circles=circles,
            ellipses=ellipses,
            marks=marks,
            metadata=MetaData(
                image_size=pre.image_size,
                deskew_angle=pre.deskew_angle,
                warnings=warnings,
            ),
        )

        with log_step("perception.parser", "label"):
            try:
                primitive_set = self.labeler.label(
                    primitive_set, bgr, pre.text_boxes, text
                )
            except Exception as e:
                warnings.append(f"labeler_failed:{e!r}")

        info(
            "perception.parser", "done",
            points=len(primitive_set.points),
            lines=len(primitive_set.lines),
            circles=len(primitive_set.circles),
            ellipses=len(primitive_set.ellipses),
            marks=len(primitive_set.marks),
            warnings=len(warnings),
        )
        return primitive_set
