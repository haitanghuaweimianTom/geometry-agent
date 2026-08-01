"""Labeling: associate OCR text labels with nearest primitives, and resolve mark
attachments to point ids (design/01 §7).
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..config import ParserConfig
from ..logging_util import info, log_step
from ..types import Circle, Line, Mark, MarkType, Point, PrimitiveSet


def _ocr_text_boxes(
    bgr, text_boxes: list[tuple[int, int, int, int]], ocr_enabled: bool
) -> list[tuple[str, float, float]]:
    """Returns list of (text, center_x, center_y) via PaddleOCR recognition.

    Falls back to empty list on any failure.
    """
    if not ocr_enabled or not text_boxes:
        return []
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception:
        return []
    try:
        # PaddleOCR 3.x API (use_textline_orientation replaces use_angle_cls;
        # show_log removed). Fall back to 2.x kwargs if 3.x rejects them.
        try:
            ocr = PaddleOCR(use_textline_orientation=True, lang="en")
        except TypeError:
            ocr = PaddleOCR(use_angle_cls=True, lang="en")
        result = ocr.predict(bgr)
    except Exception:
        try:
            ocr = PaddleOCR(use_angle_cls=True, lang="en")
            result = ocr.ocr(bgr, cls=True)
        except Exception:
            return []
    out: list[tuple[str, float, float]] = []
    if not result:
        return out
    # Normalize both 2.x and 3.x response shapes into (box, (text, conf)) pairs
    for page in result:
        if not page:
            continue
        # 3.x: page may be a dict-like with 'rec_texts'/'rec_polys'/'rec_scores'
        if isinstance(page, dict) and "rec_texts" in page:
            texts = page.get("rec_texts") or []
            polys = page.get("rec_polys") or page.get("dt_polys") or []
            for txt, poly in zip(texts, polys):
                poly = np.asarray(poly)
                xs = poly[:, 0]; ys = poly[:, 1]
                out.append((str(txt).strip(), float(np.mean(xs)), float(np.mean(ys))))
            continue
        # 2.x: list of [box, (text, conf)]
        for entry in page:
            try:
                box, rec = entry[0], entry[1]
                txt = rec[0] if isinstance(rec, (list, tuple)) else rec
                xs = [p[0] for p in box]; ys = [p[1] for p in box]
                out.append((str(txt).strip(), float(np.mean(xs)), float(np.mean(ys))))
            except Exception:
                continue
    return out


class Labeler:
    """Associates OCR labels with primitives and resolves mark vertex ids."""

    def __init__(self, config: ParserConfig):
        self.config = config

    def label(
        self,
        primitives: PrimitiveSet,
        bgr: Optional[np.ndarray],
        text_boxes: list[tuple[int, int, int, int]],
        problem_text: str = "",
        label_dist_px: float = 30.0,
    ) -> PrimitiveSet:
        # 1. OCR recognition
        ocr_items = []
        try:
            with log_step("perception.label", "ocr_recognize", n_boxes=len(text_boxes)):
                ocr_items = _ocr_text_boxes(bgr, text_boxes, self.config.ocr_enabled)
        except Exception as e:
            info("perception.label", "ocr_failed", error=repr(e))

        # 2. Assign labels to points (nearest within threshold)
        if ocr_items and primitives.points:
            self._assign_point_labels(primitives.points, ocr_items, label_dist_px)
            self._assign_curve_labels(primitives.circles, primitives.ellipses,
                                      primitives.lines, ocr_items, label_dist_px)

        # 3. Resolve mark vertex ids -> nearest point id
        self._resolve_mark_vertices(primitives.marks, primitives.points, primitives.lines)

        info(
            "perception.label", "done",
            labeled_points=sum(1 for p in primitives.points if p.label),
            marks=len(primitives.marks),
        )
        return primitives

    def _assign_point_labels(
        self, points: list[Point], ocr_items, label_dist_px: float
    ) -> None:
        used_labels: set[str] = set()
        # sort pairs by distance so closest wins
        pairs: list[tuple[float, Point, str]] = []
        for txt, tx, ty in ocr_items:
            if not txt or len(txt) > 3:
                continue
            for pt in points:
                d = float(np.hypot(pt.coords[0] - tx, pt.coords[1] - ty))
                if d < label_dist_px:
                    pairs.append((d, pt, txt))
        pairs.sort(key=lambda t: t[0])
        for d, pt, txt in pairs:
            if pt.label or txt in used_labels:
                continue
            pt.label = txt
            used_labels.add(txt)

    def _assign_curve_labels(
        self,
        circles: list[Circle],
        ellipses,
        lines: list[Line],
        ocr_items,
        label_dist_px: float,
    ) -> None:
        used: set[str] = set()
        items = sorted(
            [(float(np.hypot(c.center[0] - tx, c.center[1] - ty)), c, txt)
             for c in circles for txt, tx, ty in ocr_items
             if float(np.hypot(c.center[0] - tx, c.center[1] - ty)) < label_dist_px],
            key=lambda t: t[0],
        )
        for d, c, txt in items:
            if c.label or txt in used:
                continue
            c.label = txt
            used.add(txt)

    def _resolve_mark_vertices(
        self, marks: list[Mark], points: list[Point], lines: list[Line]
    ) -> None:
        if not points:
            return
        line_by_id = {ln.id: ln for ln in lines}
        for m in marks:
            if m.type in (MarkType.RIGHT_ANGLE, MarkType.ANGLE):
                if not m.related:
                    continue
                # find intersection of the two related lines -> nearest point
                ep_set: list[tuple[float, float]] = []
                for lid in m.related:
                    ln = line_by_id.get(lid)
                    if ln and ln.endpoints:
                        ep_set.extend(ln.endpoints)
                if not ep_set:
                    continue
                # intersection point estimate: average of endpoints that are
                # shared between the two lines (closest pair)
                if len(m.related) >= 2:
                    ln1 = line_by_id.get(m.related[0])
                    ln2 = line_by_id.get(m.related[1])
                    if ln1 and ln2 and ln1.endpoints and ln2.endpoints:
                        best = None
                        best_d = 1e9
                        for p1 in ln1.endpoints:
                            for p2 in ln2.endpoints:
                                d = float(np.hypot(p1[0] - p2[0], p1[1] - p2[1]))
                                if d < best_d:
                                    best_d = d
                                    best = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
                        if best is not None:
                            nearest = min(
                                points,
                                key=lambda p: (p.coords[0] - best[0]) ** 2
                                + (p.coords[1] - best[1]) ** 2,
                            )
                            m.vertex = nearest.id
