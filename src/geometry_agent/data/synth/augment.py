"""Style augmentation (design/09-Dataset.md §5).

Augmentations operate purely on the pixel array -- the geometry (and therefore
the GT relations) is unchanged. Includes:
  * Gaussian noise       -- simulates low-quality scans
  * Jitter (line wobble) -- simulates hand-drawn strokes (via small elastic shift)
  * Skew / rotation      -- simulates camera tilt (±5°)
  * Gaussian blur        -- simulates defocus
  * Lighting gradient    -- simulates uneven illumination

All ops preserve the input image shape.
"""
from __future__ import annotations

import random

import cv2
import numpy as np


def _gaussian_noise(img: np.ndarray, rng: random.Random) -> np.ndarray:
    sigma = rng.uniform(2.0, 12.0)
    noise = rng.gauss(0.0, sigma)  # not used directly; np.random for speed
    noise_arr = np.random.normal(0.0, sigma, img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + noise_arr, 0, 255).astype(np.uint8)


def _blur(img: np.ndarray, rng: random.Random) -> np.ndarray:
    k = int(rng.choice([3, 5]))
    k = k if k % 2 == 1 else k + 1
    return cv2.GaussianBlur(img, (k, k), 0)


def _skew(img: np.ndarray, rng: random.Random) -> np.ndarray:
    h, w = img.shape[:2]
    angle = rng.uniform(-5.0, 5.0)
    m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def _lighting_gradient(img: np.ndarray, rng: random.Random) -> np.ndarray:
    h, w = img.shape[:2]
    # random direction & strength
    angle = rng.uniform(0, 2 * np.pi)
    strength = rng.uniform(20.0, 50.0)
    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    gx, gy = np.meshgrid(xs, ys)
    grad = (np.cos(angle) * gx + np.sin(angle) * gy) / max(w, h)
    grad = (grad - grad.mean()) * strength
    out = img.astype(np.float32) + grad[:, :, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def _jitter(img: np.ndarray, rng: random.Random) -> np.ndarray:
    """Small elastic shift to simulate hand-drawn stroke wobble.

    Uses a low-amplitude smooth displacement field. Preserves shape.
    """
    h, w = img.shape[:2]
    amp = rng.uniform(1.0, 3.0)
    # small random displacement, smoothed so background stays put
    dx = np.random.uniform(-amp, amp, (h // 8 + 2, w // 8 + 2)).astype(np.float32)
    dy = np.random.uniform(-amp, amp, (h // 8 + 2, w // 8 + 2)).astype(np.float32)
    dx = cv2.resize(dx, (w, h), interpolation=cv2.INTER_CUBIC)
    dy = cv2.resize(dy, (w, h), interpolation=cv2.INTER_CUBIC)
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    map_x = (xs + dx).astype(np.float32)
    map_y = (ys + dy).astype(np.float32)
    return cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_REPLICATE)


_AUGMENT_OPS = [_gaussian_noise, _blur, _skew, _lighting_gradient, _jitter]


def augment(image: np.ndarray, rng: random.Random | None = None) -> np.ndarray:
    """Apply random style augmentation. Output has the same shape and dtype.

    Parameters
    ----------
    image : np.ndarray
        ``H x W x 3`` uint8 BGR image.
    rng : random.Random
        Source of randomness (kept stable for reproducibility).
    """
    rng = rng or random.Random()
    out = image.copy()
    # Apply 2-4 random ops
    n_ops = rng.randint(2, 4)
    ops = rng.sample(_AUGMENT_OPS, k=min(n_ops, len(_AUGMENT_OPS)))
    for op in ops:
        out = op(out, rng)
    return out
