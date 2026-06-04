"""Treatment engine (§7.5, §7.6): turn the working SVG + a recipe into a
variant SVG, either with-background (1920×1080) or transparent (edge-to-edge).

Each variant is built by:
  1. pruning a deep copy of the working tree to the selected paths,
  2. recoloring those paths per the recipe,
  3. placing them — centered/scaled on the canvas, or cropped to a tight bbox.
"""
from __future__ import annotations

import copy
import io
from dataclasses import dataclass, field

import cairosvg
from lxml import etree
from PIL import Image

from . import config
from .config import (CANVAS_W, CANVAS_H, SAFE_FRACTION, ICON_FRACTION,
                    SVG_NS, XLINK_NS, LPID_ATTR)
from .colors import normalize_hex
from .gradients import GradientSpec, parse_gradient, build_canvas_gradient
from .recipes import Treatment
from .selection import Selection
from .svg_model import WorkingSVG, BBox
from .svgutil import local_name, qn, set_paint


@dataclass
class TreatmentContext:
    model: WorkingSVG
    selection: Selection
    report: "object"            # colors.ColorReport (avoid import cycle in hints)
    grad_spec: GradientSpec | None
    _vis_bbox: dict = field(default_factory=dict)   # mark -> visible bbox cache


def build_context(model: WorkingSVG, selection: Selection, report) -> TreatmentContext:
    grad_spec = None
    if report.gradient_ids:
        defs = model.gradient_defs()
        src = defs.get(report.gradient_ids[0])
        if src is not None:
            grad_spec = parse_gradient(src, defs)
    return TreatmentContext(model=model, selection=selection, report=report,
                            grad_spec=grad_spec)


# --- include sets ------------------------------------------------------------
def _include_ids(ctx: TreatmentContext, mark: str) -> list[str]:
    if mark == "icon":
        return list(ctx.selection.icon)
    return list(ctx.selection.full)


# --- visible (rendered) bbox -------------------------------------------------
def _visible_bbox(ctx: TreatmentContext, mark: str, include: set[str]) -> BBox | None:
    """Bounding box of the artwork's actually-rendered pixels (cached per mark).

    Centering on this — not the raw vector bbox — keeps the mark visually
    centered even when the source carries invisible/fill:none guides, clip
    outlines, or stray off-mark elements that would otherwise skew the bbox and
    push the logo to a corner/edge. Output stays vector; only the placement
    offset is measured from a render.
    """
    if mark in ctx._vis_bbox:
        return ctx._vis_bbox[mark]
    vb = ctx.model.viewbox
    bb = None
    if vb:
        bb = _alpha_bbox_userspace(_copy_pruned(ctx, include), vb)
    if bb is None:
        bb = ctx.model.overall_bbox(list(include))
    ctx._vis_bbox[mark] = bb
    return bb


def _alpha_bbox_userspace(vroot: etree._Element, viewbox: BBox,
                          render_px: int = 1000) -> BBox | None:
    vbx0, vby0, vbx1, vby1 = viewbox
    vbw, vbh = vbx1 - vbx0, vby1 - vby0
    if vbw <= 0 or vbh <= 0:
        return None
    scale = render_px / max(vbw, vbh)
    w, h = max(1, round(vbw * scale)), max(1, round(vbh * scale))
    try:
        png = cairosvg.svg2png(bytestring=etree.tostring(vroot),
                               output_width=w, output_height=h)
        box = Image.open(io.BytesIO(png)).getbbox()   # non-transparent extent
    except Exception:
        return None
    if not box:
        return None
    px0, py0, px1, py1 = box
    return (vbx0 + px0 / scale, vby0 + py0 / scale,
            vbx0 + px1 / scale, vby0 + py1 / scale)


# --- prune + recolor ---------------------------------------------------------
def _copy_pruned(ctx: TreatmentContext, include: set[str]) -> etree._Element:
    """Deep-copy the working tree, drop leaves not in `include`. Defs/styles and
    all transforms are preserved."""
    vroot = copy.deepcopy(ctx.model.root)
    for el in list(vroot.iter()):
        if local_name(el) in {"path", "rect", "circle", "ellipse", "polygon",
                              "polyline", "line"}:
            if el.get(LPID_ATTR) not in include:
                el.getparent().remove(el)
    return vroot


def _recolor(ctx: TreatmentContext, vroot: etree._Element, treatment: Treatment,
             mark: str) -> None:
    icon = set(ctx.selection.icon)
    color = None
    if treatment.recolor == "white":
        color = config.WHITE
    elif treatment.recolor == "black":
        color = config.BLACK

    for el in vroot.iter():
        if local_name(el) not in {"path", "rect", "circle", "ellipse",
                                  "polygon", "polyline", "line"}:
            continue
        lpid = el.get(LPID_ATTR)
        node = ctx.model.by_lpid.get(lpid)
        if treatment.recolor == "full":
            continue
        if treatment.recolor == "split":
            # icon keeps its color/gradient; wordmark -> white (§6.2/02).
            if mark == "logo" and lpid not in icon:
                _apply(el, config.WHITE, node)
            continue
        if color is not None:
            _apply(el, color, node)


def _apply(el: etree._Element, color: str, node) -> None:
    stroke = color if (node and node.has_stroke) else None
    set_paint(el, fill=color, stroke=stroke)


# --- background resolution ---------------------------------------------------
def _resolve_bg(ctx: TreatmentContext, symbolic: str) -> tuple[str, object]:
    """Return ('solid', '#rrggbb') or ('gradient', <gradient element>)."""
    r = ctx.report
    if symbolic == "white":
        return "solid", config.WHITE
    if symbolic == "black":
        return "solid", config.BLACK
    if symbolic == "brand_a":
        return "solid", r.brand_a
    if symbolic == "brand_b":
        return "solid", r.brand_b
    if symbolic == "dark_stop":
        return "solid", ctx.grad_spec.darkest_stop() if ctx.grad_spec else config.BLACK
    if symbolic == "gradient":
        if ctx.grad_spec is None:
            return "solid", config.BLACK
        grad = build_canvas_gradient(ctx.grad_spec, "bgGradient")
        return "gradient", grad
    return "solid", config.WHITE


# --- document assembly -------------------------------------------------------
def _split_head_content(vroot: etree._Element):
    """Separate defs/style (head) from drawable content children."""
    head: list[etree._Element] = []
    content: list[etree._Element] = []
    for child in list(vroot):
        ln = local_name(child)
        if ln == "defs":
            head.extend(list(child))
        elif ln == "style":
            head.append(child)
        elif ln in ("metadata", "title", "desc"):
            continue
        else:
            content.append(child)
    return head, content


def _new_svg(width: float, height: float, viewbox: str) -> etree._Element:
    svg = etree.Element(qn("svg"), nsmap={None: SVG_NS, "xlink": XLINK_NS})
    svg.set("width", _fmt(width))
    svg.set("height", _fmt(height))
    svg.set("viewBox", viewbox)
    return svg


def _fmt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def _render_with_bg(ctx: TreatmentContext, vroot: etree._Element, art: BBox,
                    treatment: Treatment, mark: str) -> str:
    head, content = _split_head_content(vroot)
    S = CANVAS_W  # square canvas
    out = _new_svg(S, S, f"0 0 {S} {S}")

    defs = etree.SubElement(out, qn("defs"))
    for h in head:
        defs.append(h)

    kind, value = _resolve_bg(ctx, treatment.background)
    if kind == "gradient":
        defs.append(value)
        bg_fill = "url(#bgGradient)"
    else:
        bg_fill = value

    rect = etree.SubElement(out, qn("rect"))
    rect.set("x", "0"); rect.set("y", "0")
    rect.set("width", str(S)); rect.set("height", str(S))
    rect.set("fill", bg_fill)

    s = _placement_scale(ctx, art, mark, S)
    ax0, ay0, ax1, ay1 = art
    acx, acy = (ax0 + ax1) / 2.0, (ay0 + ay1) / 2.0
    tx = S / 2.0 - s * acx
    ty = S / 2.0 - s * acy
    g = etree.SubElement(out, qn("g"))
    g.set("transform", f"translate({tx:.4f},{ty:.4f}) scale({s:.6f})")
    for c in content:
        g.append(c)
    return etree.tostring(out, encoding="unicode")


def _placement_scale(ctx: TreatmentContext, art: BBox, mark: str, S: int) -> float:
    """Scale for centering the mark on the square canvas (matches the reference
    packages):

    * **logo** — keep the NATIVE composition size from the source artboard
      (`S / vb_side`), capped at SAFE_FRACTION so tightly-cropped sources don't
      bleed to the edges. Well-composed square artboards land at their designed
      size (Fire ≈50%, MpCarney ≈64%).
    * **icon** — the bare mark has an arbitrary native size, so normalize its
      longest side to ICON_FRACTION of the canvas.
    """
    ax0, ay0, ax1, ay1 = art
    maxside = max(ax1 - ax0, ay1 - ay0, 1e-6)
    if mark == "icon":
        return ICON_FRACTION * S / maxside
    vb = ctx.model.viewbox
    vb_side = max(vb[2] - vb[0], vb[3] - vb[1]) if vb else S
    vb_side = max(vb_side, 1e-6)
    return min(S / vb_side, SAFE_FRACTION * S / maxside)


def _render_transparent(ctx: TreatmentContext, vroot: etree._Element, art: BBox) -> str:
    head, content = _split_head_content(vroot)
    ax0, ay0, ax1, ay1 = art
    w, h = max(ax1 - ax0, 1e-6), max(ay1 - ay0, 1e-6)
    out = _new_svg(w, h, f"{ax0:.4f} {ay0:.4f} {w:.4f} {h:.4f}")
    if head:
        defs = etree.SubElement(out, qn("defs"))
        for hch in head:
            defs.append(hch)
    for c in content:
        out.append(c)
    return etree.tostring(out, encoding="unicode")


# --- public API --------------------------------------------------------------
def render_variant(ctx: TreatmentContext, mark: str, treatment: Treatment,
                   with_background: bool) -> str:
    """Render one variant SVG string for `mark` ('icon'|'logo')."""
    include = set(_include_ids(ctx, mark))
    vroot = _copy_pruned(ctx, include)
    _recolor(ctx, vroot, treatment, mark)
    art = _visible_bbox(ctx, mark, include)
    if art is None:
        art = ctx.model.viewbox or (0.0, 0.0, float(CANVAS_W), float(CANVAS_H))
    if with_background:
        return _render_with_bg(ctx, vroot, art, treatment, mark)
    return _render_transparent(ctx, vroot, art)
