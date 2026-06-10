"""Engine-wide constants. The fixture (§10) and locked spec (§5.2) drive these."""
import os
import re

# --- Canvas -----------------------------------------------------------------
# LOCKED artboards (owner standard): every with-background LOGO format is a
# fixed 1920x1080 artboard; every with-background ICON format is a fixed
# 1080x1080 SQUARE artboard. The mark is proportionally scaled (never stretched
# or skewed) to fit within SAFE_FRACTION of the artboard and centered (balanced)
# on its visible bbox. Rasters export at @EXPORT_SCALE.
CANVAS_W = 1920
CANVAS_H = 1080
ICON_CANVAS = 1080
# The mark occupies 60% of the artboard: its binding side scales to exactly
# 60% of the corresponding canvas dimension, the other side proportional.
SAFE_FRACTION = 0.60


def canvas_for(mark: str) -> tuple[int, int]:
    """(width, height) of the with-background artboard for 'icon' | 'logo'."""
    if mark == "icon":
        return ICON_CANVAS, ICON_CANVAS
    return CANVAS_W, CANVAS_H

# --- Transparent raster (§5.2) ----------------------------------------------
PNG_WIDTH = 1080  # transparent PNGs: 1080px wide (logical), height proportional.

# --- Raster export quality ---------------------------------------------------
# Rasters are exported at @Nx pixel density for crisp, high-quality output
# (vector SVG/PDF stay resolution-independent). Default @2x: logo JPG 3840x2160,
# icon JPG 2160x2160, transparent PNG 2160px wide.
EXPORT_SCALE = int(os.environ.get("LOGO_EXPORT_SCALE", "2"))
JPG_QUALITY = int(os.environ.get("LOGO_JPG_QUALITY", "95"))

# --- Canonical colors --------------------------------------------------------
WHITE = "#ffffff"
BLACK = "#000000"

# Relative-luminance threshold to call a background "light" vs "dark" (§6.1).
LIGHT_LUMINANCE_THRESHOLD = 0.5

# Colors at/above this luminance are treated as "white-ish" (background/default),
# at/below WHITE/near-black handling for brand-color ranking (§6.1).
NEAR_WHITE_LUMINANCE = 0.92
NEAR_BLACK_LUMINANCE = 0.06

# --- Naming (§5.3) -----------------------------------------------------------
ICON_STEM = "Icon"
LOGO_STEM = "Logo"

# --- AI segmentation (vision-in-the-loop) -----------------------------------
# When ANTHROPIC_API_KEY is set, the "Auto-detect" button renders the artboard
# and asks Claude to read it like a designer and propose the logo/icon boxes;
# the geometric selection.auto_segment is the offline fallback. The model is
# overridable; it defaults to Fable 5, the most capable model. LOGO_AI_MAX_PX
# caps the rendered preview's width (keeps the request light, stays legible).
AI_SEGMENT_MODEL = os.environ.get("LOGO_AI_MODEL", "claude-fable-5")
AI_SEGMENT_MAX_PX = int(os.environ.get("LOGO_AI_MAX_PX", "1400"))


def variant_filename(stem: str, index: int, ext: str) -> str:
    """`Icon 01.jpg` ... `Logo 05.svg` — zero-padded two digits, space before
    the number (§5.3)."""
    return f"{stem} {index:02d}.{ext}"


# Path separators, parent refs, and characters illegal in filenames on common
# OSes — plus Unicode bidi controls (U+202A-202E etc.) that can spoof how a
# filename renders. The brand becomes a folder name AND the `.ai`/`.eps`/zip
# stem, so it must be a single safe component — never let it escape the temp dir.
_UNSAFE_NAME = re.compile(
    r'[<>:"/\\|?*\x00-\x1f\x7f‎‏‪-‮⁦-⁩﻿]')


def safe_brand(brand: str | None) -> str:
    """Sanitize a CSR-supplied brand for use as a filename/folder component.

    Strips path separators, ``..``, and reserved characters; collapses runs of
    whitespace; trims leading/trailing dots and spaces; caps length. Falls back
    to ``Logo`` when nothing safe remains. (Defends against path traversal like
    ``../../etc`` and zip-slip — §2 stateless temp-dir isolation.)"""
    b = _UNSAFE_NAME.sub(" ", (brand or "")).replace("..", " ")
    b = re.sub(r"\s+", " ", b).strip(" .")
    return (b or "Logo")[:80]


def root_folder_name(brand: str) -> str:
    """`[Brand Name] Files` (§5.1), with the brand sanitized to a safe component."""
    return f"{safe_brand(brand)} Files"


# SVG namespaces used throughout.
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
NSMAP = {"svg": SVG_NS, "xlink": XLINK_NS}

# Attribute injected onto every drawable leaf to correlate svgelements geometry
# with the lxml tree (see svg_model.py). Survives serialization round-trips.
LPID_ATTR = "data-lpid"
