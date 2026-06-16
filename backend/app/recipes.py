"""The §6 treatment recipes, encoded as data.

A *treatment* = a recolor + a background (§6). The engine turns each row below
into a variant SVG. Backgrounds are symbolic and resolved per-logo (§6.1):

    white      -> #ffffff
    black      -> #000000
    brand_a    -> darker brand color   (e.g. navy #112630)
    brand_b    -> vivid brand color    (e.g. red  #ec1c24); for a 1-color logo,
                  a deep in-scheme shade of the brand color
    gradient   -> rebuilt canvas-scale brand gradient, full-bleed (§7.5)
    dark_stop  -> solid sampled from the gradient's darkest stop (§6.4/05)

Recolor values:

    full   -> ADAPTIVE: fills kept; on a colored background every color that
              reads stays, and each one that doesn't is swapped to the most
              similar color from the logo's own palette that reads (else
              white/black, preferring white on saturated brand colors). The
              treatment engine's layer-aware contrast guard implements this —
              so a red-on-navy logo keeps its red on the navy background, a
              mascot keeps every readable color, and a purple-on-purple logo
              becomes the classic white knockout. Never a color outside the
              logo's scheme.
    white  -> every fill (incl. gradient-filled paths) -> #fff  (mono)
    black  -> every fill -> #000                                 (mono)
    split  -> icon group unchanged; wordmark group -> #fff (transparent logo
              02 — the ready-for-dark-backgrounds cut)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Treatment:
    index: int          # 1-based file index -> `Icon 01`, `Logo 02`, ...
    background: str      # symbolic background (see module docstring); "" == none
    recolor: str         # full | white | black | split


# --- §6.2 SOLID logo, with background ---------------------------------------
# The identity sheet a designer ships: true colors on white, the two brand-
# background usages (adaptive, in-scheme), and the guaranteed mono pair.
SOLID_LOGO = [
    Treatment(1, "white", "full"),
    Treatment(2, "brand_a", "full"),    # adaptive on the dark brand color
    Treatment(3, "brand_b", "full"),    # adaptive on the vivid brand color
    Treatment(4, "white", "black"),     # mono black
    Treatment(5, "black", "white"),     # mono white (reversed)
]

# --- §6.3 SOLID icon, with background ----------------------------------------
SOLID_ICON = [
    Treatment(1, "white", "full"),
    Treatment(2, "brand_a", "full"),
    Treatment(3, "brand_b", "full"),
    Treatment(4, "white", "black"),
    Treatment(5, "black", "white"),
]

# --- §6.4 GRADIENT logo, with background ------------------------------------
# White knockout is the FIXED treatment on the gradient background (§8 rule 5).
# On black the mark goes WHITE — the designer standard (Orova): a gradient's tone
# shifts across the mark, so only white reads cleanly on black.
GRADIENT_LOGO = [
    Treatment(1, "white", "full"),
    Treatment(2, "gradient", "white"),   # hero: white knockout on full-bleed gradient
    Treatment(3, "black", "white"),      # white knockout on black (Orova standard)
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
