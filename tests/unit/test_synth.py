"""Unit tests for the programmatic synthesis engine (design/09 §4)."""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest

from geometry_agent.data.loader import load_dataset, load_image
from geometry_agent.data.synth.augment import augment
from geometry_agent.data.synth.constructor import ConstructedScene
from geometry_agent.data.synth.generator import SynthGenerator
from geometry_agent.data.synth.renderer import render
from geometry_agent.data.synth.templates import (
    CircleInscribedTemplate,
    CircleTangentTemplate,
    EllipseFocusTemplate,
    TriangleTemplate,
    TwoCirclesTemplate,
)
from geometry_agent.types import NodeType, RelType, VerifyState


# ---------------------------------------------------------------------------
# 1. TriangleTemplate
# ---------------------------------------------------------------------------
def test_triangle_template_constructs_valid_scene():
    tpl = TriangleTemplate()
    params = tpl.sample_params(random.Random(0))
    scene = tpl.construct(params)
    assert isinstance(scene, ConstructedScene)

    # 3 points + 3 segments
    assert len(scene.primitives.points) == 3
    assert len(scene.primitives.lines) == 3
    for L in scene.primitives.lines:
        assert L.length is not None and L.length > 0

    # Triangle inequality
    pts = [p.coords for p in scene.primitives.points]
    sides = sorted(
        np.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
        for i, j in [(0, 1), (1, 2), (2, 0)]
    )
    assert sides[0] + sides[1] > sides[2]

    # On relations: each point is on >=1 segment; total On edges >= 6 (each
    # endpoint on each of its two segments).
    on_edges = [e for e in scene.graph.edges if e.rel == RelType.ON]
    assert len(on_edges) >= 6
    for e in on_edges:
        assert e.verified == VerifyState.TRUE


# ---------------------------------------------------------------------------
# 2. CircleTangentTemplate
# ---------------------------------------------------------------------------
def test_circle_tangent_has_tangent_on_perpendicular():
    tpl = CircleTangentTemplate()
    params = tpl.sample_params(random.Random(1))
    scene = tpl.construct(params)

    rels = {e.rel for e in scene.graph.edges}
    assert RelType.TANGENT in rels, f"Tangent missing; got {rels}"
    assert RelType.ON in rels
    assert RelType.PERPENDICULAR in rels, f"Perpendicular missing; got {rels}"
    assert RelType.CENTER in rels
    assert RelType.TANGENT_POINT in rels

    # Tangent edge carries tangent_point attr pointing to a real point node
    tan_edges = [e for e in scene.graph.edges if e.rel == RelType.TANGENT]
    assert len(tan_edges) >= 1
    tp_id = tan_edges[0].attrs.get("tangent_point")
    assert tp_id is not None
    node_ids = {n.id for n in scene.graph.nodes}
    assert tp_id in node_ids

    # all edges verified=true (GT)
    for e in scene.graph.edges:
        assert e.verified == VerifyState.TRUE


# ---------------------------------------------------------------------------
# 3. render output
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tpl_cls", [
    TriangleTemplate, CircleTangentTemplate, CircleInscribedTemplate,
    EllipseFocusTemplate, TwoCirclesTemplate,
])
def test_render_returns_nonempty_image(tpl_cls):
    tpl = tpl_cls()
    params = tpl.sample_params(random.Random(2))
    scene = tpl.construct(params)
    img = render(scene)
    assert isinstance(img, np.ndarray)
    assert img.ndim == 3 and img.shape[2] == 3
    assert img.dtype == np.uint8
    assert img.shape[0] > 0 and img.shape[1] > 0
    # not all-white (something was drawn)
    assert img.min() < 255


# ---------------------------------------------------------------------------
# 4. augment preserves shape
# ---------------------------------------------------------------------------
def test_augment_preserves_shape():
    tpl = TriangleTemplate()
    scene = tpl.construct(tpl.sample_params(random.Random(3)))
    img = render(scene)
    aug = augment(img, random.Random(7))
    assert isinstance(aug, np.ndarray)
    assert aug.shape == img.shape
    assert aug.dtype == img.dtype


# ---------------------------------------------------------------------------
# 5. SynthGenerator.generate
# ---------------------------------------------------------------------------
def test_generator_generate_returns_n_scenes():
    g = SynthGenerator(rng_seed=0)
    scenes = g.generate(5)
    assert len(scenes) == 5
    for s in scenes:
        assert isinstance(s, ConstructedScene)
        assert s.template_name
        assert len(s.graph.nodes) > 0
        # all GT edges verified
        for e in s.graph.edges:
            assert e.verified == VerifyState.TRUE


def test_generator_generate_with_template_filter():
    g = SynthGenerator(rng_seed=0)
    scenes = g.generate(4, template_names=["triangle_basic"])
    assert len(scenes) == 4
    assert all(s.template_name == "triangle_basic" for s in scenes)


# ---------------------------------------------------------------------------
# 6. generate_dataset + load_dataset round-trip
# ---------------------------------------------------------------------------
def test_generate_dataset_and_load_roundtrip(tmp_path: Path):
    g = SynthGenerator(rng_seed=11)
    recs = g.generate_dataset(3, tmp_path)
    assert len(recs) == 3
    # files written
    assert (tmp_path / "synth_000000.png").exists()
    assert (tmp_path / "synth_000000.json").exists()

    loaded = load_dataset(tmp_path)
    assert len(loaded) == 3
    rec0 = loaded[0]
    assert "image" in rec0 and "objects" in rec0 and "relations" in rec0
    assert "dsl" in rec0 and "answer" in rec0
    assert rec0["size"][0] > 0 and rec0["size"][1] > 0

    img = load_image(tmp_path / rec0["image"])
    assert img.ndim == 3 and img.shape[2] == 3

    # at least one verified relation per record (GT non-empty)
    assert any(r.get("verified") == "true" for r in rec0["relations"])
