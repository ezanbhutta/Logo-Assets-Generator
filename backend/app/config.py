"""Engine-wide constants. The fixture (§10) and locked spec (§5.2) drive these."""

# --- Canvas (§5.2) -----------------------------------------------------------
CANVAS_W = 1920
CANVAS_H = 1080
# Logo's longest side <= ~65% of the corresponding canvas dimension (§5.2/§7.6).
SAFE_FRACTION = 0.65

# --- Transparent raster (§5.2) ----------------------------------------------
PNG_WIDTH = 1080  # transparent PNGs: 1080px wide, height proportional.

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
