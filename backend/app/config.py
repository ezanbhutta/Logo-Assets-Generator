"""Engine-wide constants. The fixture (§10) and locked spec (§5.2) drive these."""
import os
import re

# --- Canvas -----------------------------------------------------------------
# FIXED 1920x1080 artboard on every with-background format (locked standard).
# The logo is centered and scaled to fit; rasters export at @EXPORT_SCALE.
CANVAS_W = 1920
CANVAS_H = 1080
# Logo's longest side <= ~65% of the corresponding canvas dimension, centered.
SAFE_FRACTION = 0.65
# Icon variants: re-centered, longest side normalized to this fraction of the
# shorter canvas dimension.
ICON_FRACTION = 0.30

# --- Transparent raster (§5.2) ----------------------------------------------
PNG_WIDTH = 1080  # transparent PNGs: 1080px wide (logical), height proportional.

# --- Raster export quality ---------------------------------------------------
# Rasters are exported at @Nx pixel density for crisp, high-quality output
# (vector SVG/PDF stay resolution-independent). Default @2x: JPG 3840x2160,
# transparent PNG 2160px wide.
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
