"""Engine-wide constants. The fixture (§10) and locked spec (§5.2) drive these."""
import os

# --- Canvas -----------------------------------------------------------------
# SQUARE artboards, matching the ground-truth reference packages (Fire Systems
# 1080², MpCarney 1200²) — exported at @EXPORT_SCALE (default @2x → 2160²).
CANVAS_W = 1080
CANVAS_H = 1080
# Logo cap: the lockup keeps its NATIVE composition size from the source
# artboard (designers compose with margins), but never exceeds this fraction of
# the canvas — protects tightly-cropped sources from touching the edges.
SAFE_FRACTION = 0.66
# Icon variants are re-centered and normalized to this fraction of the canvas
# (the bare mark from a lockup has an arbitrary native size). Matches the
# reference icon sizing (~0.29–0.31 longest side).
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


def root_folder_name(brand: str) -> str:
    """`[Brand Name] Files` (§5.1)."""
    return f"{brand} Files"


# SVG namespaces used throughout.
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
NSMAP = {"svg": SVG_NS, "xlink": XLINK_NS}

# Attribute injected onto every drawable leaf to correlate svgelements geometry
# with the lxml tree (see svg_model.py). Survives serialization round-trips.
LPID_ATTR = "data-lpid"
