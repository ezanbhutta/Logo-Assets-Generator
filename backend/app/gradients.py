"""Gradient parsing + canvas-scale rebuild (§7.5, §8 rule 4).

For a gradient background we MUST NOT paste the mark-sized gradient onto the
full canvas rect (it would render in a tiny corner and go flat). Instead we
build a NEW gradient: same stop colors/offsets, same direction, geometry set to
span the whole rect via ``gradientUnits="objectBoundingBox"``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from lxml import etree

from .config import XLINK_NS
from .colors import normalize_hex, luminance
from .svgutil import local_name, qn, style_dict

XLINK_HREF = f"{{{XLINK_NS}}}href"


@dataclass
class GradientSpec:
    kind: str                       # 'linear' | 'radial'
    stops: list[tuple[float, str, float]]   # (offset, color, opacity)
    direction: tuple[float, float]  # unit vector (linear only; radial -> (1,0))

    def darkest_stop(self) -> str:
        solids = [(c, luminance(c)) for _, c, _ in self.stops if normalize_hex(c)]
        if not solids:
            return "#000000"
        return min(solids, key=lambda t: t[1])[0]


def _stop_color(stop: etree._Element) -> str:
    sd = style_dict(stop)
    return (sd.get("stop-color") or stop.get("stop-color") or "#000000").strip()


def _stop_opacity(stop: etree._Element) -> float:
    sd = style_dict(stop)
    raw = sd.get("stop-opacity") or stop.get("stop-opacity") or "1"
    try:
        return float(raw)
    except ValueError:
        return 1.0


def _parse_offset(raw: str | None) -> float:
    if not raw:
        return 0.0
    raw = raw.strip()
    try:
        return float(raw[:-1]) / 100.0 if raw.endswith("%") else float(raw)
    except ValueError:
        return 0.0


def _coord(raw: str | None, default: float) -> float:
    if raw is None:
        return default
    raw = raw.strip()
    try:
        return float(raw[:-1]) / 100.0 if raw.endswith("%") else float(raw)
    except ValueError:
        return default


def _collect_stops(grad: etree._Element,
                   defs: dict[str, etree._Element],
                   seen: set[str] | None = None) -> list[tuple[float, str, float]]:
    """Stops on the element, or inherited via xlink:href (Illustrator pattern)."""
    seen = seen or set()
    stops = [
        (_parse_offset(st.get("offset")), _stop_color(st), _stop_opacity(st))
        for st in grad if local_name(st) == "stop"
    ]
    if stops:
        return stops
    href = grad.get(XLINK_HREF) or grad.get("href")
    if href and href.startswith("#"):
        ref = href[1:]
        if ref in defs and ref not in seen:
            return _collect_stops(defs[ref], defs, seen | {ref})
    return stops


def parse_gradient(grad: etree._Element,
                   defs: dict[str, etree._Element]) -> GradientSpec:
    kind = "radial" if local_name(grad) == "radialGradient" else "linear"
    stops = _collect_stops(grad, defs)

    if kind == "linear":
        x1 = _coord(grad.get("x1"), 0.0)
        y1 = _coord(grad.get("y1"), 0.0)
        x2 = _coord(grad.get("x2"), 1.0)
        y2 = _coord(grad.get("y2"), 0.0)
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            dx, dy = 1.0, 0.0
        n = math.hypot(dx, dy)
        direction = (dx / n, dy / n)
    else:
        direction = (1.0, 0.0)

    if not stops:  # degenerate gradient -> black->black so it still renders
        stops = [(0.0, "#000000", 1.0), (1.0, "#000000", 1.0)]
    return GradientSpec(kind=kind, stops=stops, direction=direction)


def build_canvas_gradient(spec: GradientSpec, new_id: str) -> etree._Element:
    """Build a full-bleed gradient (objectBoundingBox) spanning the whole rect,
    preserving the source stops and (for linear) the direction/angle (§7.5)."""
    if spec.kind == "radial":
        grad = etree.Element(qn("radialGradient"))
        grad.set("id", new_id)
        grad.set("gradientUnits", "objectBoundingBox")
        grad.set("cx", "0.5")
        grad.set("cy", "0.5")
        grad.set("r", "0.75")   # covers the corners (corner dist = 0.707)
    else:
        ux, uy = spec.direction
        # Span the unit box corner-to-corner along the gradient axis so both end
        # stops reach the canvas edges at the source angle (full bleed).
        corners = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]
        projs = [(cx * ux + cy * uy, (cx, cy)) for cx, cy in corners]
        (_, start) = min(projs, key=lambda t: t[0])
        (_, end) = max(projs, key=lambda t: t[0])
        grad = etree.Element(qn("linearGradient"))
        grad.set("id", new_id)
        grad.set("gradientUnits", "objectBoundingBox")
        grad.set("x1", f"{start[0]:.4f}")
        grad.set("y1", f"{start[1]:.4f}")
        grad.set("x2", f"{end[0]:.4f}")
        grad.set("y2", f"{end[1]:.4f}")

    for offset, color, opacity in spec.stops:
        st = etree.SubElement(grad, qn("stop"))
        st.set("offset", f"{offset:.4f}")
        st.set("stop-color", color)
        if opacity < 0.999:
            st.set("stop-opacity", f"{opacity:.4f}")
    return grad
