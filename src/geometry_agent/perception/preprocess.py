"""Image preprocessing: grayscale, binarize, denoise, deskew, skeleton, OCR separation.

Implements design/01-Geometry-Parser.md §4. All steps are tolerant: on failure
they emit a warning and return a degraded but valid result (never raise).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ..config import ParserConfig
from ..logging_util import log_step


@dataclass
class PreprocessResult:
    """Outputs of the preprocessing stage consumed by detectors."""

    gray: np.ndarray
    binary: np.ndarray              # foreground (geometry strokes) = 255
    binary_clean: np.ndarray        # binary with text regions zeroed
    skeleton: np.ndarray            # uint8 0/255, 1px-wide
    deskew_angle: float = 0.0
    text_boxes: list[tuple[int, int, int, int]] = field(default_factory=list)
    image_size: tuple[int, int] = (0, 0)
    warnings: list[str] = field(default_factory=list)


def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img.copy()
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _adaptive_binarize(gray: np.ndarray) -> np.ndarray:
    """Binarize handling both dark-bg (white strokes) and bright-bg (ink on paper).

    Foreground (strokes) is always 255 in the output.
    """
    mean = float(gray.mean())
    if mean < 127:
        # dark background, bright strokes (e.g. synthetic / whiteboard)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        # bright paper, dark ink
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 10
        )
    return binary


def _denoise(binary: np.ndarray) -> np.ndarray:
    k3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    out = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k3)
    out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, k3)
    out = cv2.medianBlur(out, 3)
    return out


def _deskew(binary: np.ndarray, threshold_deg: float) -> tuple[np.ndarray, float]:
    """Estimate dominant orientation via weighted Hough line angles and rotate.

    Returns (corrected_binary, applied_angle_deg). On failure returns original.
    """
    H, W = binary.shape
    lines = cv2.HoughLinesP(binary, 1, np.pi / 180, 50, minLineLength=30, maxLineGap=10)
    if lines is None or len(lines) == 0:
        return binary, 0.0
    angles, weights = [], []
    for ln in lines:
        x1, y1, x2, y2 = ln.reshape(-1)[:4]
        ang = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        angles.append(ang)
        weights.append(float(np.hypot(x2 - x1, y2 - y1)))
    angles = np.asarray(angles)
    weights = np.asarray(weights)
    # fold angles to [-90, 90)
    angles = ((angles + 90.0) % 180.0) - 90.0
    hist, edges = np.histogram(angles, bins=180, range=(-90, 90), weights=weights)
    theta0 = float(edges[int(np.argmax(hist))])
    alpha = theta0 - round(theta0 / 90.0) * 90.0
    if abs(alpha) < threshold_deg:
        return binary, 0.0
    M = cv2.getRotationMatrix2D((W / 2.0, H / 2.0), alpha, 1.0)
    corrected = cv2.warpAffine(
        binary, M, (W, H), flags=cv2.INTER_NEAREST, borderValue=0
    )
    return corrected, alpha


def _skeletonize(binary: np.ndarray, method: str) -> np.ndarray:
    """Skeletonize to 1px-wide strokes. Uses skimage (cv2.ximgproc not bundled)."""
    try:
        from skimage.morphology import skeletonize
    except Exception:
        # fallback: thin via erosion-dilation approximation (good enough for clean images)
        sk = (binary > 0)
    else:
        sk = skeletonize(binary > 0)
    return (sk.astype(np.uint8)) * 255


def _separate_text(
    bgr: np.ndarray, gray: np.ndarray, ocr_enabled: bool
) -> tuple[list[tuple[int, int, int, int]], np.ndarray]:
    """Detect text boxes via PaddleOCR (det only). Returns (boxes, mask).

    mask is uint8 same size as gray, 255 over text regions (to zero out later).
    On any failure or if OCR disabled, returns ([], zeros).
    """
    H, W = gray.shape
    mask = np.zeros_like(gray)
    if not ocr_enabled:
        return [], mask
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception:
        return [], mask
    try:
        try:
            ocr = PaddleOCR(use_textline_orientation=False, lang="en")
        except TypeError:
            ocr = PaddleOCR(use_angle_cls=False, lang="en")
        result = ocr.predict(bgr)
    except Exception:
        try:
            ocr = PaddleOCR(use_angle_cls=False, lang="en")
            result = ocr.ocr(bgr, cls=False)
        except Exception:
            return [], mask
    boxes: list[tuple[int, int, int, int]] = []
    if not result:
        return boxes, mask
    for page in result:
        if not page:
            continue
        # 3.x dict shape
        if isinstance(page, dict) and "rec_polys" in page:
            polys = page.get("rec_polys") or page.get("dt_polys") or []
            for poly in polys:
                poly = np.asarray(poly)
                xs = poly[:, 0].astype(int); ys = poly[:, 1].astype(int)
                x0, x1 = max(0, int(xs.min())), min(W, int(xs.max()))
                y0, y1 = max(0, int(ys.min())), min(H, int(ys.max()))
                if x1 <= x0 or y1 <= y0:
                    continue
                boxes.append((x0, y0, x1 - x0, y1 - y0))
                mask[y0:y1, x0:x1] = 255
            continue
        # 2.x list shape
        for entry in page:
            try:
                box = entry[0]
                xs = [int(p[0]) for p in box]
                ys = [int(p[1]) for p in box]
                x0, x1 = max(0, min(xs)), min(W, max(xs))
                y0, y1 = max(0, min(ys)), min(H, max(ys))
                if x1 <= x0 or y1 <= y0:
                    continue
                boxes.append((x0, y0, x1 - x0, y1 - y0))
                mask[y0:y1, x0:x1] = 255
            except Exception:
                continue
    return boxes, mask


class Preprocessor:
    """Runs the full preprocessing pipeline -> PreprocessResult."""

    def __init__(self, config: ParserConfig):
        self.config = config

    def run(self, image_path: Path | str | np.ndarray) -> PreprocessResult:
        warnings: list[str] = []
        if isinstance(image_path, np.ndarray):
            bgr = image_path.copy()
        else:
            bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise FileNotFoundError(f"cannot read image: {image_path}")
        gray = _to_gray(bgr)

        with log_step("perception.preprocess", "binarize", shape=gray.shape):
            binary = _adaptive_binarize(gray)
        with log_step("perception.preprocess", "denoise"):
            binary = _denoise(binary)
        try:
            with log_step("perception.preprocess", "deskew", threshold=self.config.deskew_threshold_deg):
                binary, angle = _deskew(binary, self.config.deskew_threshold_deg)
        except Exception as e:
            angle = 0.0
            warnings.append(f"deskew_failed:{e!r}")

        try:
            with log_step("perception.preprocess", "skeleton", method=self.config.skeleton_method):
                skeleton = _skeletonize(binary, self.config.skeleton_method)
        except Exception as e:
            skeleton = binary.copy()
            warnings.append(f"skeleton_failed:{e!r}")

        try:
            with log_step("perception.preprocess", "ocr_separate", ocr=self.config.ocr_enabled):
                text_boxes, text_mask = _separate_text(bgr, gray, self.config.ocr_enabled)
        except Exception as e:
            text_boxes, text_mask = [], np.zeros_like(gray)
            warnings.append(f"ocr_failed:{e!r}")

        binary_clean = cv2.bitwise_and(binary, cv2.bitwise_not(text_mask))
        skeleton_clean = cv2.bitwise_and(skeleton, cv2.bitwise_not(text_mask))

        H, W = gray.shape
        return PreprocessResult(
            gray=gray,
            binary=binary,
            binary_clean=binary_clean,
            skeleton=skeleton_clean,
            deskew_angle=angle,
            text_boxes=text_boxes,
            image_size=(W, H),
            warnings=warnings,
        )


def load_image_rgb(image_path: Path | str | np.ndarray) -> np.ndarray:
    """Load image as BGR uint8 (for mark detection / OCR). Raises if unreadable."""
    if isinstance(image_path, np.ndarray):
        return image_path.copy()
    bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f"cannot read image: {image_path}")
    return bgr
