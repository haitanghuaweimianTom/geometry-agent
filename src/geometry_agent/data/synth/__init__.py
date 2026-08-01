"""Programmatic geometry synthesis engine (design/09-Dataset.md §4).

Pipeline: Template -> ParamSampler -> GeometryConstructor -> Renderer -> Augment.

Exports the public ``SynthGenerator`` plus the ``ConstructedScene`` artifact and
the ``render``/``render_to_file``/``augment`` helpers.
"""
from __future__ import annotations

from .constructor import ConstructedScene, ConstructSpec, GeometryConstructor, construct_scene
from .templates import (
    TEMPLATES,
    CircleInscribedTemplate,
    CircleTangentTemplate,
    EllipseFocusTemplate,
    TemplateBase,
    TriangleTemplate,
    TwoCirclesTemplate,
)
from .augment import augment
from .renderer import render, render_to_file
from .generator import SynthGenerator

__all__ = [
    "ConstructedScene",
    "ConstructSpec",
    "GeometryConstructor",
    "construct_scene",
    "TEMPLATES",
    "TemplateBase",
    "TriangleTemplate",
    "CircleTangentTemplate",
    "CircleInscribedTemplate",
    "EllipseFocusTemplate",
    "TwoCirclesTemplate",
    "render",
    "render_to_file",
    "augment",
    "SynthGenerator",
]
