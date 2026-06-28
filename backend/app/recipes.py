"""The §6 treatment recipes.

A *treatment* = a recolor + a background (§6). The engine turns each row below
into a variant SVG.

The with-background SOLID set is the owner's trained recipe (PACK FRESH CLUB),
built per-logo from its real palette by ``build_solid`` — not a static table,
because slots 02–04 depend on the brand colors:

  01  white background      · the PRIMARY logo exactly as authored (no recolor,
                              no contrast "fixing" — the designer's own colors).
  02  dark background       · the SAME full-colour logo on the darkest shade used
                              in the logo, or BLACK when the logo has no dark
                              shade. The adaptive guard only rescues a colour that
                              would vanish on the dark field.
  03 · 04  the two brand     · the colour-SWAP pair — a flat color-B logo on the
       colours as fields       color-A field and a flat color-A logo on the
                               color-B field (e.g. yellow-on-blue / blue-on-
                               yellow). When the two colours would clash on each
                               other (``colors_harmonize`` is False) they fall
                               back to the designer mono: a black mark on the
                               lighter field, a white mark on the darker field.
  05  white background      · the BLACK one-colour monochrome.
  06  black background      · the WHITE one-colour monochrome (reversed) — the
                              owner ships both monos as their own slides.

The transparent set also carries both one-colour marks.

Backgrounds are literal ``#rrggbb`` (resolved per-logo) or symbolic for the
gradient set (``gradient`` / ``dark_stop`` / ``brand_a`` / ``brand_b``).

Recolor values:
    full   -> keep the authored fills (the PRIMARY, on white: exactly as drawn).
              On a coloured field the adaptive, layer-aware contrast guard swaps
              only the colours that would vanish, to an in-scheme substitute —
              this is what keeps a 3+-colour mascot readable on a brand field.
    keep   -> the SAME authored fills (slot 02, "put the same on the dark
              field"): a colour is swapped ONLY when it fails against the field
              itself (canvas-only — never against a sibling stroke), so a layered
              wordmark lands on black exactly as authored.
    flat   -> recolor EVERY fill/stroke to ``Treatment.color`` (the swap colour
              or a knockout). A single flat colour — no contrast guard.
    white  -> every fill -> #fff  (mono)
    black  -> every fill -> #000  (mono)
    split  -> icon group unchanged; wordmark group -> #fff (transparent logo 02).
"""

from dataclasses import dataclass

from . import colors, config


@dataclass(frozen=True)
class Treatment:
    index: int          # 1-based file index -> `Icon 01`, `Logo 02`, ...
    background: str      # literal "#rrggbb" OR symbolic (gradient set); "" == none
    recolor: str         # full | flat | white | black | split
    color: str | None = None   # explicit hex for recolor == 'flat'


# --- §6.2/6.3 SOLID set, built per-logo from its palette ---------------------
def _dark_background(report) -> str:
    """Slot-02 field: the darkest genuinely-dark colour in the logo (a navy, a
    deep brown), or BLACK when the logo has no dark shade — the owner's rule."""
    darks = [c for c in report.solids
             if colors.normalize_hex(c) and colors.luminance(c) < 0.20]
    return min(darks, key=colors.luminance) if darks else config.BLACK


def _brand_pair(report) -> tuple[str, str] | None:
    """The logo's two brand colours (a = darker, b = more vivid) when it really
    has exactly two distinct chromatic colours — the case the swap recipe is for.
    A 1-colour, neutral, or 3+-colour mark returns None (handled separately)."""
    chrom: list[str] = []
    for c in report.solids:
        hx = colors.normalize_hex(c)
        if not hx or not colors._is_brand_color(hx):
            continue
        if all(colors._distance(hx, u) > 0.02 for u in chrom):
            chrom.append(hx)
    if len(chrom) != 2:
        return None
    return report.brand_a, report.brand_b


def build_solid(report, mark: str) -> list["Treatment"]:
    """The 5 with-background treatments for a SOLID logo/icon, per the owner's
    trained recipe (see module docstring). ``mark`` is 'logo' | 'icon' — the set
    is identical (the same rule applies to icons)."""
    slots = [
        Treatment(1, config.WHITE, "full"),               # primary, exactly as authored
        Treatment(2, _dark_background(report), "keep"),   # the SAME logo on dark / black
    ]

    pair = _brand_pair(report)
    if pair is not None:
        a, b = pair                                        # a = darker, b = more vivid
        if colors.colors_harmonize(a, b):
            # color-swap: each brand field carries the OTHER brand colour, flat.
            slots += [Treatment(3, a, "flat", color=b),
                      Treatment(4, b, "flat", color=a)]
        else:
            # clash fallback: a mono knockout reads on each brand field — white on
            # the darker, black on the lighter (best_knockout picks per field).
            slots += [Treatment(3, a, "flat", color=colors.best_knockout(a)),
                      Treatment(4, b, "flat", color=colors.best_knockout(b))]
    else:
        # 1-colour / neutral / 3+-colour: keep the brand fields but let the
        # adaptive guard hold contrast (an exception to refine over time).
        slots += [Treatment(3, report.brand_a, "full"),
                  Treatment(4, report.brand_b, "full")]

    slots += [
        Treatment(5, config.WHITE, "black"),    # black one-colour monochrome (on white)
        Treatment(6, config.BLACK, "white"),    # white one-colour monochrome (on black, reversed)
    ]
    return slots


# --- §6.4 GRADIENT logo, with background ------------------------------------
# White knockout is the FIXED treatment on the gradient background (§8 rule 5).
# On black the mark goes WHITE — the designer standard (Orova): a gradient's tone
# shifts across the mark, so only white reads cleanly on black.
GRADIENT_LOGO = [
    Treatment(1, config.WHITE, "full"),
    Treatment(2, "gradient", "white"),   # hero: white knockout on full-bleed gradient
    Treatment(3, config.BLACK, "white"), # white knockout on black (Orova standard)
    Treatment(4, config.WHITE, "black"),
    Treatment(5, "dark_stop", "white"),
]

GRADIENT_ICON = GRADIENT_LOGO


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


def with_bg_recipes(mark: str, report, is_gradient: bool) -> list["Treatment"]:
    """Return the 5 with-background treatments for `mark` ('icon'|'logo'). The
    SOLID set is built from the logo's real palette (`report`); the GRADIENT set
    is the fixed designer standard."""
    if is_gradient:
        return GRADIENT_ICON if mark == "icon" else GRADIENT_LOGO
    return build_solid(report, mark)


def transparent_recipes(mark: str) -> list["Treatment"]:
    """Return the transparent treatments for `mark` ('icon'|'logo')."""
    return TRANSPARENT_ICON if mark == "icon" else TRANSPARENT_LOGO
