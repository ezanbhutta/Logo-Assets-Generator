"""The §6 treatment recipes, encoded as data.

A *treatment* = a recolor + a background (§6). The engine turns each row below
into a variant SVG. Backgrounds are symbolic and resolved per-logo (§6.1):

    white      -> #ffffff
    black      -> #000000
    brand_a    -> darker brand color   (e.g. navy #112630)
    brand_b    -> vivid brand color    (e.g. red  #ec1c24); falls back to black
                  for a 1-color logo
    gradient   -> rebuilt canvas-scale brand gradient, full-bleed (§7.5)
    dark_stop  -> solid sampled from the gradient's darkest stop (§6.4/05)

Recolor values:

    full   -> fills unchanged
    white  -> every fill (incl. gradient-filled paths) -> #fff
    black  -> every fill -> #000
    split  -> icon group unchanged; wordmark group -> #fff (logo only)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Treatment:
    index: int          # 1-based file index -> `Icon 01`, `Logo 02`, ...
    background: str      # symbolic background (see module docstring); "" == none
    recolor: str         # full | white | black | split


# --- §6.2 SOLID logo, with background ---------------------------------------
SOLID_LOGO = [
    Treatment(1, "white", "full"),
    Treatment(2, "brand_a", "split"),
    Treatment(3, "brand_b", "white"),
    Treatment(4, "white", "black"),
    Treatment(5, "black", "white"),
]

# --- §6.3 SOLID icon, with background (no wordmark -> no split) --------------
SOLID_ICON = [
    Treatment(1, "white", "full"),
    Treatment(2, "brand_a", "full"),   # icon in its own color
    Treatment(3, "brand_b", "white"),
    Treatment(4, "white", "black"),
    Treatment(5, "black", "white"),
]

# --- §6.4 GRADIENT logo, with background ------------------------------------
# White knockout is the FIXED treatment on the gradient background (§8 rule 5).
GRADIENT_LOGO = [
    Treatment(1, "white", "full"),
    Treatment(2, "gradient", "white"),   # hero: white knockout on full-bleed gradient
    Treatment(3, "black", "white"),
    Treatment(4, "white", "black"),
    Treatment(5, "dark_stop", "white"),
]

# --- §6.5 GRADIENT icon, with background ------------------------------------
GRADIENT_ICON = [
    Treatment(1, "white", "full"),
    Treatment(2, "gradient", "white"),
    Treatment(3, "black", "white"),
    Treatment(4, "white", "black"),
    Treatment(5, "dark_stop", "white"),
]

# --- §6.6 Transparent LOGO (edge-to-edge, no background) ---------------------
TRANSPARENT_LOGO = [
    Treatment(1, "", "full"),
    Treatment(2, "", "split"),
    Treatment(3, "", "white"),
    Treatment(4, "", "black"),
]

# --- §6.7 Transparent ICON ---------------------------------------------------
TRANSPARENT_ICON = [
    Treatment(1, "", "full"),
    Treatment(2, "", "white"),
    Treatment(3, "", "black"),
]


def with_bg_recipes(mark: str, is_gradient: bool) -> list[Treatment]:
    """Return the 5 with-background treatments for `mark` ('icon'|'logo')."""
    if is_gradient:
        return GRADIENT_ICON if mark == "icon" else GRADIENT_LOGO
    return SOLID_ICON if mark == "icon" else SOLID_LOGO


def transparent_recipes(mark: str) -> list[Treatment]:
    """Return the transparent treatments for `mark` ('icon'|'logo')."""
    return TRANSPARENT_ICON if mark == "icon" else TRANSPARENT_LOGO
