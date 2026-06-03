"""Treatment engine (§7.5, §7.6): turn the working SVG + a recipe into a
variant SVG, either with-background (1920×1080) or transparent (edge-to-edge).

Each variant is built by:
  1. pruning a deep copy of the working tree to the selected paths,
  2. recoloring those paths per the recipe,
  3. placing them — centered/scaled on the canvas, or cropped to a tight bbox.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from lxml import etree

from . import config
from .config import CANVAS_W, CANVAS_H, SAFE_FRACTION, SVG_NS, XLINK_NS, LPID_ATTR
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
                    treatment: Treatment) -> str:
    head, content = _split_head_content(vroot)
    out = _new_svg(CANVAS_W, CANVAS_H, f"0 0 {CANVAS_W} {CANVAS_H}")

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
    rect.set("width", str(CANVAS_W)); rect.set("height", str(CANVAS_H))
    rect.set("fill", bg_fill)

    # Center + scale the artwork within the safe margins (§5.2/§7.6).
    ax0, ay0, ax1, ay1 = art
    aw, ah = max(ax1 - ax0, 1e-6), max(ay1 - ay0, 1e-6)
    s = min(SAFE_FRACTION * CANVAS_W / aw, SAFE_FRACTION * CANVAS_H / ah)
    acx, acy = (ax0 + ax1) / 2.0, (ay0 + ay1) / 2.0
    tx = CANVAS_W / 2.0 - s * acx
    ty = CANVAS_H / 2.0 - s * acy
    g = etree.SubElement(out, qn("g"))
    g.set("transform", f"translate({tx:.4f},{ty:.4f}) scale({s:.6f})")
    for c in content:
        g.append(c)
    return etree.tostring(out, encoding="unicode")


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
    art = ctx.model.overall_bbox(list(include))
    if art is None:
        art = ctx.model.viewbox or (0.0, 0.0, float(CANVAS_W), float(CANVAS_H))
    if with_background:
        return _render_with_bg(ctx, vroot, art, treatment)
    return _render_transparent(ctx, vroot, art)
