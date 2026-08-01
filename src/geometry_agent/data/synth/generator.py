"""SynthGenerator: orchestrates template -> construct -> render -> augment -> dump.

Public API (design/09 §4.1):
  * :meth:`SynthGenerator.generate`               -- in-memory scenes
  * :meth:`SynthGenerator.generate_dataset`        -- writes PNG + JSON to disk
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import cv2

from .augment import augment
from .constructor import ConstructedScene
from .renderer import render
from .templates import TEMPLATES, TemplateBase


class SynthGenerator:
    """Programmatic synthesis generator.

    Parameters
    ----------
    rng_seed : int
        Seed for the top-level :class:`random.Random` used for template choice
        and parameter sampling. ``np.random`` inside augment derives its own
        state from this seed for reproducibility.
    """

    def __init__(self, rng_seed: int = 0):
        self.rng_seed = rng_seed

    # ----- in-memory generation ----- #
    def generate(self, n: int,
                 template_names: list[str] | None = None) -> list[ConstructedScene]:
        """Generate ``n`` constructed scenes by sampling templates + params."""
        rng = random.Random(self.rng_seed)
        names = template_names or list(TEMPLATES.keys())
        for nm in names:
            if nm not in TEMPLATES:
                raise ValueError(f"Unknown template: {nm}. Available: {list(TEMPLATES)}")
        scenes: list[ConstructedScene] = []
        for _ in range(n):
            name = rng.choice(names)
            template: TemplateBase = TEMPLATES[name]()
            params = template.sample_params(rng)
            scenes.append(template.construct(params))
        return scenes

    # ----- dataset generation ----- #
    def generate_dataset(self, n: int, out_dir: str | Path,
                         template_names: list[str] | None = None,
                         augment_prob: float = 0.5,
                         image_size: tuple[int, int] = (400, 320)) -> list[dict[str, Any]]:
        """Generate ``n`` scenes, render + augment, write PNG + JSON to ``out_dir``.

        Returns the list of annotation records (also written as JSON).
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        rng = random.Random(self.rng_seed)
        # seed np.random for reproducible augment
        try:
            import numpy as np
            np.random.seed(self.rng_seed)
        except Exception:  # pragma: no cover
            pass

        scenes = self.generate(n, template_names=template_names)
        records: list[dict[str, Any]] = []
        for i, scene in enumerate(scenes):
            style = {"image_size": image_size}
            img = render(scene, style=style)
            if rng.random() < augment_prob:
                img = augment(img, rng)
            fname = f"synth_{i:06d}.png"
            jname = f"synth_{i:06d}.json"
            cv2.imwrite(str(out_dir / fname), img)
            record = _scene_to_record(scene, fname, img.shape[:2])
            with open(out_dir / jname, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            records.append(record)
        return records


# --------------------------------------------------------------------------- #
# Annotation record builder (design/09 §3 COCO-like format)
# --------------------------------------------------------------------------- #
def _scene_to_record(scene: ConstructedScene, image_fname: str,
                     image_shape: tuple[int, int]) -> dict[str, Any]:
    h, w = int(image_shape[0]), int(image_shape[1])
    objects: list[dict[str, Any]] = []
    for p in scene.primitives.points:
        objects.append({
            "type": "Point",
            "id": p.id,
            "label": p.label,
            "coords": [float(p.coords[0]), float(p.coords[1])],
        })
    for L in scene.primitives.lines:
        obj: dict[str, Any] = {
            "type": L.type.value.capitalize() if L.type.value != "line" else "Line",
            "id": L.id,
            "label": L.label,
        }
        if L.endpoints:
            obj["endpoints"] = [[float(e[0]), float(e[1])] for e in L.endpoints]
        if L.length is not None:
            obj["length"] = float(L.length)
        objects.append(obj)
    for c in scene.primitives.circles:
        objects.append({
            "type": "Circle",
            "id": c.id,
            "label": c.label,
            "center": [float(c.center[0]), float(c.center[1])],
            "radius": float(c.radius),
        })
    for e in scene.primitives.ellipses:
        objects.append({
            "type": "Ellipse",
            "id": e.id,
            "label": e.label,
            "center": [float(e.center[0]), float(e.center[1])],
            "semi_major": float(e.semi_major),
            "semi_minor": float(e.semi_minor),
            "rotation": float(e.rotation),
            "foci": [[float(f[0]), float(f[1])] for f in e.foci],
        })
    for poly in scene.primitives.polygons:
        objects.append({
            "type": "Polygon",
            "id": poly.id,
            "label": poly.label,
            "poly_type": poly.poly_type,
            "vertices": [[float(v[0]), float(v[1])] for v in poly.vertices],
        })

    relations: list[dict[str, Any]] = []
    node_by_id = {n.id: n for n in scene.graph.nodes}
    for edge in scene.graph.edges:
        rec: dict[str, Any] = {
            "rel": edge.rel.value,
            "src": edge.src,
            "dst": edge.dst,
            "verified": edge.verified.value,
        }
        # carry human-readable labels
        src_n = node_by_id.get(edge.src)
        dst_n = node_by_id.get(edge.dst)
        if src_n:
            rec["src_label"] = src_n.label or src_n.id
        if dst_n:
            rec["dst_label"] = dst_n.label or dst_n.id
        if edge.attrs:
            rec["attrs"] = _jsonable(edge.attrs)
        relations.append(rec)

    return {
        "image": image_fname,
        "size": [w, h],
        "template": scene.template_name,
        "objects": objects,
        "relations": relations,
        "dsl": scene.dsl,
        "answer": scene.answer,
        "problem_text": scene.problem_text,
        "params": _jsonable(scene.params),
    }


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    return str(obj)
