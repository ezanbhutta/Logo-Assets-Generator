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
from .colors import normalize_hex, contrast_ratio, best_knockout
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
        if local_name(el) in _LEAVES:
            lpid = el.get(LPID_ATTR)
            # only prune tagged artwork leaves; untagged clip/defs paths stay so
            # clips keep working (an emptied clipPath hides the clipped artwork).
            if lpid and lpid not in include:
                el.getparent().remove(el)
    return vroot


# Below this fg/bg contrast ratio an element is effectively invisible -> knock
# it out to a visible color (e.g. a single-color logo on its own brand bg).
MIN_CONTRAST = 2.2

_LEAVES = {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line"}


def _recolor(ctx: TreatmentContext, vroot: etree._Element, treatment: Treatment,
             mark: str, bg: tuple[str, object] | None = None) -> None:
    icon = set(ctx.selection.icon)
    color = None
    if treatment.recolor == "white":
        color = config.WHITE
    elif treatment.recolor == "black":
        color = config.BLACK

    for el in vroot.iter():
        if local_name(el) not in _LEAVES:
            continue
        lpid = el.get(LPID_ATTR)
        if not lpid:
            continue                              # clip/defs path — not artwork
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

    # Contrast guard: ensure every element reads against what's behind it.
    if bg is not None:
        _ensure_contrast(ctx, vroot, treatment, mark, bg)


def _effective_fg(treatment: Treatment, mark: str, lpid: str, node,
                  icon: set[str]) -> str | None:
    """The solid color an element ends up as for this treatment, or None when it
    keeps a gradient (which spans a range and is left alone)."""
    r = treatment.recolor
    if r == "white":
        return config.WHITE
    if r == "black":
        return config.BLACK
    if r == "split" and mark == "logo" and lpid not in icon:
        return config.WHITE
    return normalize_hex(node.fill) if node else None


def _ensure_contrast(ctx: TreatmentContext, vroot: etree._Element,
                     treatment: Treatment, mark: str, bg: tuple[str, object]) -> None:
    """Flip any element that would blend into its BACKDROP to white/black —
    whichever reads. The backdrop is what's actually behind the element: a
    larger element drawn beneath it (e.g. an icon's gear), or the canvas
    background. Layer-aware so:
      * detail sitting on a colored/gradient shape is kept (white circuit on a
        purple gear stays white, not knocked to black vs the white canvas),
      * mono treatments don't merge detail into the shape — the detail flips so
        the pattern stays visible.
    A single-color mark on its own brand background still knocks out (no shape
    beneath it -> backdrop is the canvas)."""
    bg_kind, bg_value = bg
    canvas = normalize_hex(bg_value) if bg_kind == "solid" else "gradient"

    icon = set(ctx.selection.icon)
    leaves = [el for el in vroot.iter() if local_name(el) in _LEAVES]
    nodes = [ctx.model.by_lpid.get(el.get(LPID_ATTR)) for el in leaves]
    fgs = [_effective_fg(treatment, mark, el.get(LPID_ATTR), n, icon)
           for el, n in zip(leaves, nodes)]

    for i, el in enumerate(leaves):
        node, fg = nodes[i], fgs[i]
        if fg is None or not node or not node.bbox:
            continue                              # keeps a gradient -> colorful, leave it
        cx, cy = node.centroid
        backdrop = canvas
        # the topmost LARGER element drawn beneath this one that covers its center
        for j in range(i):
            bn = nodes[j]
            if (bn and bn.bbox and bn.area > node.area
                    and bn.bbox[0] <= cx <= bn.bbox[2]
                    and bn.bbox[1] <= cy <= bn.bbox[3]):
                backdrop = "gradient" if fgs[j] is None else fgs[j]
        if backdrop in (None, "gradient"):
            continue                              # gradient/unknown backdrop -> white/black reads
        if contrast_ratio(fg, backdrop) < MIN_CONTRAST:
            knock = best_knockout(backdrop)
            _apply(el, knock, node)
            fgs[i] = knock                         # so elements above see the new color


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
                    mark: str, bg: tuple[str, object]) -> str:
    head, content = _split_head_content(vroot)
    W, H = CANVAS_W, CANVAS_H
    out = _new_svg(W, H, f"0 0 {W} {H}")

    defs = etree.SubElement(out, qn("defs"))
    for h in head:
        defs.append(h)

    kind, value = bg
    if kind == "gradient":
        defs.append(value)
        bg_fill = "url(#bgGradient)"
    else:
        bg_fill = value

    rect = etree.SubElement(out, qn("rect"))
    rect.set("x", "0"); rect.set("y", "0")
    rect.set("width", str(W)); rect.set("height", str(H))
    rect.set("fill", bg_fill)

    s = _placement_scale(art, mark)
    ax0, ay0, ax1, ay1 = art
    acx, acy = (ax0 + ax1) / 2.0, (ay0 + ay1) / 2.0
    tx = W / 2.0 - s * acx
    ty = H / 2.0 - s * acy
    g = etree.SubElement(out, qn("g"))
    g.set("transform", f"translate({tx:.4f},{ty:.4f}) scale({s:.6f})")
    for c in content:
        g.append(c)
    return etree.tostring(out, encoding="unicode")


def _placement_scale(art: BBox, mark: str) -> float:
    """Scale to center the mark on the fixed 1920x1080 canvas.

    * **logo** — fit within SAFE_FRACTION of each canvas dimension (§5.2).
    * **icon** — normalize the longest side to ICON_FRACTION of the shorter
      canvas dimension (the bare mark has an arbitrary native size).
    """
    ax0, ay0, ax1, ay1 = art
    aw, ah = max(ax1 - ax0, 1e-6), max(ay1 - ay0, 1e-6)
    if mark == "icon":
        return ICON_FRACTION * min(CANVAS_W, CANVAS_H) / max(aw, ah)
    return min(SAFE_FRACTION * CANVAS_W / aw, SAFE_FRACTION * CANVAS_H / ah)


def _render_transparent(ctx: TreatmentContext, vroot: etree._Element, art: BBox) -> str:
    head, content = _split_head_content(vroot)
    ax0, ay0, ax1, ay1 = art
    w, h = max(ax1 - ax0, 1e-6), max(ay1 - ay0, 1e-6)
    # Zero-origin viewBox: translate the artwork to (0,0) and frame it at
    # "0 0 w h". A non-zero viewBox origin is valid SVG but Finder/Illustrator
    # render it with white letterboxing (looks like padding) — this makes the
    # transparent SVG truly edge-to-edge in every viewer. The translate also
    # shifts userSpaceOnUse gradient space, so gradients stay aligned.
    out = _new_svg(w, h, f"0 0 {w:.4f} {h:.4f}")
    if head:
        defs = etree.SubElement(out, qn("defs"))
        for hch in head:
            defs.append(hch)
    g = etree.SubElement(out, qn("g"))
    g.set("transform", f"translate({-ax0:.4f},{-ay0:.4f})")
    for c in content:
        g.append(c)
    return etree.tostring(out, encoding="unicode")


# --- public API --------------------------------------------------------------
def render_variant(ctx: TreatmentContext, mark: str, treatment: Treatment,
                   with_background: bool) -> str:
    """Render one variant SVG string for `mark` ('icon'|'logo')."""
    include = set(_include_ids(ctx, mark))
    vroot = _copy_pruned(ctx, include)
    # Resolve the background first so recolor can enforce fg/bg contrast.
    bg = _resolve_bg(ctx, treatment.background) if with_background else None
    _recolor(ctx, vroot, treatment, mark, bg)
    art = _visible_bbox(ctx, mark, include)
    if art is None:
        art = ctx.model.viewbox or (0.0, 0.0, float(CANVAS_W), float(CANVAS_H))
    if with_background:
        return _render_with_bg(ctx, vroot, art, mark, bg)
    return _render_transparent(ctx, vroot, art)
