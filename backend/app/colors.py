"""Color/gradient detection, brand-color ranking, and the scope classifier
(§6.1, §7.4, §9).

svgelements would flatten gradient fills, so detection reads the resolved
authored fill strings from the path model (``PathNode.fill``).
"""
from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass, field

from svgelements import Color

from . import config
from .svgutil import local_name, qn
from .svg_model import WorkingSVG, PathNode

_URL_RE = re.compile(r"url\(['\"]?#([^)'\"]+)['\"]?\)")

# Saturation below this == neutral (white / black / gray) -> not a brand color.
_NEUTRAL_SAT = 0.10


# --- color utilities ---------------------------------------------------------
def normalize_hex(value: str | None) -> str | None:
    """Return '#rrggbb' lowercase for a solid color, else None (none/url/bad)."""
    if not value:
        return None
    v = value.strip().lower()
    if v in ("none", "transparent", "currentcolor") or v.startswith("url("):
        return None
    try:
        c = Color(v)
        return f"#{c.red:02x}{c.green:02x}{c.blue:02x}"
    except Exception:
        return None


def gradient_ref(value: str | None) -> str | None:
    """Extract the gradient id from a `url(#id)` fill, else None."""
    if not value:
        return None
    m = _URL_RE.search(value)
    return m.group(1) if m else None


def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore


def luminance(hex_color: str) -> float:
    """WCAG relative luminance, 0 (black) .. 1 (white)."""
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def saturation(hex_color: str) -> float:
    r, g, b = _rgb(hex_color)
    return colorsys.rgb_to_hsv(r, g, b)[1]


def is_light(hex_color: str) -> bool:
    return luminance(hex_color) >= config.LIGHT_LUMINANCE_THRESHOLD


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two hex colors (1.0 == identical)."""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def best_knockout(bg_hex: str) -> str:
    """White or black — whichever is more visible on `bg_hex`."""
    return config.WHITE if contrast_ratio(config.WHITE, bg_hex) >= \
        contrast_ratio(config.BLACK, bg_hex) else config.BLACK


# An in-palette substitute must really read (body-text contrast), or we fall
# back to white/black. Looser bars produce muddy tone-on-tone marks.
SUBSTITUTE_CONTRAST = 4.5
# Designer fallback: white is the classic mark on a saturated brand color
# (think white-on-red, white-on-navy) — prefer it whenever it clears ~3:1,
# even where pure math would score black slightly higher; black only on
# genuinely light backgrounds (yellow, cream, light gray) where white fails.
_WHITE_PREF_CONTRAST = 3.0


def designer_knockout(bg_hex: str) -> str:
    """White when it reads on `bg_hex` (>= ~3:1), else black."""
    return config.WHITE if contrast_ratio(config.WHITE, bg_hex) >= \
        _WHITE_PREF_CONTRAST else config.BLACK


def _distance(a: str, b: str) -> float:
    """Perceptually-weighted RGB distance — which palette color *feels* closest."""
    (r1, g1, b1), (r2, g2, b2) = _rgb(a), _rgb(b)
    return 2 * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + 3 * (b1 - b2) ** 2


def best_substitute(fg: str, bg: str, palette: list[str]) -> str:
    """The color a designer would swap `fg` to so it reads on `bg`, staying in
    the logo's own scheme.

    Preference order: the most *similar* palette color that genuinely reads on
    `bg` (>= SUBSTITUTE_CONTRAST) — so a brown mascot outline on a brown brand
    background becomes the mascot's own cream, not stark white — else the
    designer white/black fallback. Never returns `fg` itself or anything that
    blends into the background."""
    candidates = [c for c in palette
                  if c and c != fg and contrast_ratio(c, bg) >= SUBSTITUTE_CONTRAST]
    if candidates:
        return min(candidates, key=lambda c: _distance(c, fg))
    return designer_knockout(bg)


def mix_hex(a: str, b: str, t: float) -> str:
    """Linear mix of two hex colors: t=0 -> a, t=1 -> b."""
    (r1, g1, b1), (r2, g2, b2) = _rgb(a), _rgb(b)
    def ch(x1: float, x2: float) -> int:
        return max(0, min(255, round((x1 + (x2 - x1) * t) * 255)))
    return f"#{ch(r1, r2):02x}{ch(g1, g2):02x}{ch(b1, b2):02x}"


def shade_of(brand_hex: str) -> str:
    """A deep shade of the brand color — the in-scheme alternate background for
    a 1-color logo (replaces the old plain-black fallback). Darkened just until
    white reads comfortably on it; a near-black brand color shades to ~itself."""
    shade = mix_hex(brand_hex, config.BLACK, 0.45)
    t = 0.45
    while contrast_ratio(config.WHITE, shade) < SUBSTITUTE_CONTRAST and t < 0.9:
        t += 0.1
        shade = mix_hex(brand_hex, config.BLACK, t)
    return shade


def _is_brand_color(hex_color: str) -> bool:
    """Chromatic (has hue) and not near-white -> eligible as a brand color."""
    return saturation(hex_color) >= _NEUTRAL_SAT and luminance(hex_color) < config.NEAR_WHITE_LUMINANCE


# --- detection report --------------------------------------------------------
@dataclass
class ColorReport:
    classification: str                 # 'solid' | 'gradient' | 'manual'
    reasons: list[str] = field(default_factory=list)      # out-of-scope reasons
    solids: list[str] = field(default_factory=list)       # distinct hex, prominence-ordered
    gradient_ids: list[str] = field(default_factory=list)
    brand_a: str = config.BLACK
    brand_b: str = config.BLACK
    swatches: list[dict] = field(default_factory=list)    # for the confirm UI

    @property
    def is_gradient(self) -> bool:
        return self.classification == "gradient"

    @property
    def supported(self) -> bool:
        return self.classification in ("solid", "gradient")


# --- scope classification (§7.4 / §9) ---------------------------------------
def _scope_reasons(model: WorkingSVG) -> list[str]:
    """Detect out-of-scope features that force a 'manual' flag (§9)."""
    reasons: list[str] = []
    root = model.root

    def present(tag: str) -> bool:
        return next(root.iter(qn(tag)), None) is not None

    if present("image"):
        reasons.append("embedded raster image (<image>)")
    if present("meshgradient") or present("mesh"):
        reasons.append("mesh / freeform gradient")
    if present("filter"):
        reasons.append("filter effect / drop shadow")
    if present("text") or present("tspan"):
        reasons.append("live (un-outlined) text")
    if present("color-profile"):
        reasons.append("ICC / spot color profile")

    # filter applied via attribute or style, and in-artwork transparency.
    transparent = False
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        style = el.get("style", "")
        if el.get("filter") or "filter:" in style:
            if "filter effect / drop shadow" not in reasons:
                reasons.append("filter effect / drop shadow")
        if "icc-color(" in style or "icc-color(" in (el.get("fill") or ""):
            if "ICC / spot color profile" not in reasons:
                reasons.append("ICC / spot color profile")
        # opacity / fill-opacity < 1 anywhere in the artwork = in-art transparency.
        for prop in ("opacity", "fill-opacity"):
            raw = el.get(prop) or _style_val(style, prop)
            if raw is not None:
                try:
                    if float(raw) < 0.999:
                        transparent = True
                except ValueError:
                    pass
        # rgba()/hsla() fills with alpha.
        fill = (el.get("fill") or "") + ";" + style
        if "rgba(" in fill or "hsla(" in fill:
            transparent = True
    if transparent:
        reasons.append("in-artwork transparency")

    return reasons


def _style_val(style: str, prop: str) -> str | None:
    for chunk in style.split(";"):
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            if k.strip() == prop:
                return v.strip()
    return None


# --- brand ranking (§6.1) ----------------------------------------------------
def _rank_brand_colors(nodes: list[PathNode],
                       exclude: set[str] | None = None) -> tuple[list[str], str, str]:
    """Return (prominence-ordered distinct solids, brand_a, brand_b).

    `exclude` = colors the CSR removed as strays (e.g. an off-black artifact);
    they're dropped from brand ranking so they never drive a background (§3.5)."""
    exclude = {e.lower() for e in (exclude or set())}
    weight: dict[str, float] = {}
    order: list[str] = []
    for n in nodes:
        hx = normalize_hex(n.fill)
        if not hx:
            continue
        if hx not in weight:
            weight[hx] = 0.0
            order.append(hx)
        # prominence = total area, with a floor so zero-area shapes still count.
        weight[hx] += max(n.area, 1.0)

    solids = sorted(order, key=lambda h: weight[h], reverse=True)
    candidates = [h for h in solids if _is_brand_color(h) and h not in exclude]

    if not candidates:
        # Neutral-only logo (e.g. a black wordmark): no chromatic color to use,
        # so the alternate backgrounds come from the logo's own NEUTRAL scale —
        # a charcoal and a light gray tint of its ink (in-scheme; three identical
        # black slots would be useless). On the light gray the dark mark still
        # reads, so that slot keeps the logo in its true color.
        base = min(solids, key=luminance) if solids else config.BLACK
        if luminance(base) > 0.5:          # all-light neutral logo (rare)
            return solids, mix_hex(base, config.BLACK, 0.75), mix_hex(base, config.BLACK, 0.45)
        return solids, mix_hex(base, config.WHITE, 0.28), mix_hex(base, config.WHITE, 0.85)
    if len(candidates) == 1:
        # 1-color logo: brand-B = a deep shade of the brand color, so the
        # alternate background stays in the logo's own scheme (owner standard;
        # previously plain black).
        return solids, candidates[0], shade_of(candidates[0])

    top2 = candidates[:2]
    # brand-A = the darker; brand-B = the more vivid/primary.
    brand_a = min(top2, key=luminance)
    brand_b = max(top2, key=saturation)
    if brand_b == brand_a:  # both extremes landed on one color
        brand_b = next(c for c in top2 if c != brand_a)
    return solids, brand_a, brand_b


# --- public entry ------------------------------------------------------------
def detect(model: WorkingSVG, lpids: list[str] | None = None,
           exclude: set[str] | None = None,
           brand_a_override: str | None = None,
           brand_b_override: str | None = None) -> ColorReport:
    """Analyze the artwork (all leaves, or the subset `lpids`) -> ColorReport.

    `exclude` drops CSR-removed strays from brand ranking; the brand overrides
    let the confirm UI lock the palette explicitly."""
    nodes = model.ink_nodes if lpids is None else [model.by_lpid[i] for i in lpids if i in model.by_lpid]

    grad_ids: list[str] = []
    for n in nodes:
        gid = gradient_ref(n.fill)
        if gid and gid in model.gradient_defs() and gid not in grad_ids:
            grad_ids.append(gid)

    solids, brand_a, brand_b = _rank_brand_colors(nodes, exclude)
    brand_a = normalize_hex(brand_a_override) or brand_a
    brand_b = normalize_hex(brand_b_override) or brand_b
    reasons = _scope_reasons(model)

    if reasons:
        classification = "manual"
    elif grad_ids:
        classification = "gradient"
    else:
        classification = "solid"

    swatches: list[dict] = []
    for hx in solids:
        swatches.append({
            "type": "solid", "value": hx,
            "brand": hx in (brand_a, brand_b),
            "luminance": round(luminance(hx), 3),
        })
    for gid in grad_ids:
        swatches.append({"type": "gradient", "value": gid, "brand": True})

    return ColorReport(
        classification=classification,
        reasons=reasons,
        solids=solids,
        gradient_ids=grad_ids,
        brand_a=brand_a,
        brand_b=brand_b,
        swatches=swatches,
    )
