"""Treatment engine (§7.5, §7.6): turn the working SVG + a recipe into a
variant SVG, either with-background (logo 1920×1080, icon 1080×1080 square)
or transparent (edge-to-edge).

Each variant is built by:
  1. pruning a deep copy of the working tree to the selected paths,
  2. recoloring those paths per the recipe — the ADAPTIVE contrast guard keeps
     every color that reads on the background and swaps each one that doesn't
     to an in-scheme substitute (the logo's own palette first, then white/black),
  3. placing them — proportionally scaled to 60% of the canvas and centered,
     or cropped to a tight bbox.
"""
from __future__ import annotations

import copy
import io
from dataclasses import dataclass, field

import cairosvg
from lxml import etree
from PIL import Image

from . import config
from .config import (canvas_for, safe_fraction_for, SVG_NS, XLINK_NS, LPID_ATTR)
from .colors import (normalize_hex, contrast_ratio, best_knockout,
                     best_substitute, designer_knockout, gradient_ref, mix_hex,
                     saturation)
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
    _grad_avg: dict = field(default_factory=dict)   # lpid -> avg gradient tone cache


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
# Neutral-on-neutral pairs (gray on charcoal) get no help from hue, so they
# need real luminance contrast; chromatic pairs (orange on brown, red on navy)
# read at lower ratios because hue separates them.
_NEUTRAL_PAIR_CONTRAST = 3.0
_CHROMATIC_SAT = 0.15


def _reads_on(fg: str, bg: str) -> bool:
    """Does `fg` read on `bg` to a designer's eye? Chromatic pairs pass at
    MIN_CONTRAST (hue does part of the work); a pair with no real hue between
    them must clear the stricter neutral bar."""
    c = contrast_ratio(fg, bg)
    if c >= _NEUTRAL_PAIR_CONTRAST:
        return True
    if c < MIN_CONTRAST:
        return False
    return max(saturation(fg), saturation(bg)) >= _CHROMATIC_SAT

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


def _gradient_avg(ctx: TreatmentContext, node) -> str | None:
    """A gradient fill's representative solid — the average of its stops. Lets
    the guard judge whether a gradient-filled element reads on a background the
    way a designer eyeballs its overall tone. Cached per element."""
    if node is None:
        return None
    if node.lpid in ctx._grad_avg:
        return ctx._grad_avg[node.lpid]
    avg = None
    gid = gradient_ref(node.fill)
    if gid:
        defs = ctx.model.gradient_defs()
        grad = defs.get(gid)
        if grad is not None:
            stops = [hx for _, c, _ in parse_gradient(grad, defs).stops
                     if (hx := normalize_hex(c))]
            if stops:
                avg = stops[0]
                for i, s in enumerate(stops[1:], start=2):
                    avg = mix_hex(avg, s, 1.0 / i)             # running mean
    ctx._grad_avg[node.lpid] = avg
    return avg


def _palette(ctx: TreatmentContext) -> list[str]:
    """The logo's own colors — the only substitution candidates the adaptive
    recolor may use (plus the white/black designer fallback)."""
    return [hx for c in getattr(ctx.report, "solids", []) if (hx := normalize_hex(c))]


def _ensure_contrast(ctx: TreatmentContext, vroot: etree._Element,
                     treatment: Treatment, mark: str, bg: tuple[str, object]) -> None:
    """Make every element read against its BACKDROP — what's actually behind it:
    a larger element drawn beneath (e.g. an icon's gear), or the canvas. This is
    the adaptive recolor: on a brand background the artwork keeps every color
    that reads, and a designer-grade substitute fixes each one that doesn't.

      * **full treatments** — a failing color is swapped to the most similar
        color from the logo's OWN palette that reads (in-scheme first: a brown
        mascot outline on the brown brand bg becomes the mascot's cream), else
        white/black with the designer preference for white on saturated brand
        colors. Gradient-filled elements are judged by their average stop tone
        on non-white backdrops — a vivid gradient stays itself on black; one
        that vanishes is swapped to a readable solid.
      * **mono (white/black) treatments** — nested detail flips white<->black so
        the pattern stays visible; never to a palette color (mono stays mono).
      * Layer-aware throughout: white detail on a purple gear is judged against
        the gear, not the canvas, so it survives the white background."""
    bg_kind, bg_value = bg
    canvas = normalize_hex(bg_value) if bg_kind == "solid" else "gradient"
    adaptive = treatment.recolor == "full"
    palette = _palette(ctx) if adaptive else []

    icon = set(ctx.selection.icon)
    leaves = [el for el in vroot.iter() if local_name(el) in _LEAVES]
    nodes = [ctx.model.by_lpid.get(el.get(LPID_ATTR)) for el in leaves]
    fgs = [_effective_fg(treatment, mark, el.get(LPID_ATTR), n, icon)
           for el, n in zip(leaves, nodes)]

    for i, el in enumerate(leaves):
        node, fg = nodes[i], fgs[i]
        if not node or not node.bbox:
            continue
        backdrop = canvas
        # The topmost LARGER element drawn beneath this one that FULLY contains
        # it (small tolerance). Full containment — not centroid-in-bbox — so a
        # mark that merely brushes a shape (a mascot's ears poking past its
        # body) is judged against the canvas it actually sits on.
        nb = node.bbox
        eps = 0.06 * max(nb[2] - nb[0], nb[3] - nb[1], 1e-6)
        for j in range(i):
            bn = nodes[j]
            if (bn and bn.bbox and bn.area > node.area
                    and bn.bbox[0] <= nb[0] + eps and bn.bbox[1] <= nb[1] + eps
                    and bn.bbox[2] >= nb[2] - eps and bn.bbox[3] >= nb[3] - eps):
                if fgs[j] is not None:
                    backdrop = fgs[j]
                else:
                    avg = _gradient_avg(ctx, bn)
                    backdrop = avg if avg else "gradient"
        if backdrop in (None, "gradient"):
            continue                              # unknown backdrop -> white/black reads

        if fg is None:
            # Gradient-filled element kept by a full treatment: judge its average
            # tone. On white (the canonical full-color slot) it is always kept.
            if not adaptive or backdrop == config.WHITE:
                continue
            avg = _gradient_avg(ctx, node)
            if avg is None or _reads_on(avg, backdrop):
                continue
            sub = best_substitute(avg, backdrop, palette)
            _apply(el, sub, node)
            fgs[i] = sub
            continue

        if not _reads_on(fg, backdrop):
            if adaptive:
                knock = best_substitute(fg, backdrop, palette)
            else:
                knock = best_knockout(backdrop)    # mono stays mono
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
    if symbolic == "tint":
        # Soft in-scheme tint for the mono-black slot; plain white when the brand
        # already has a light color or is single-color (getattr -> back-compat).
        return "solid", getattr(r, "tint", None) or config.WHITE
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
    W, H = canvas_for(mark)
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
    """Uniform scale (proportional — never stretched or skewed) so the mark's
    binding side spans its artboard's safe fraction: the LOGO 60% of 1920x1080,
    the ICON 42% of 1080x1080 (icons sit smaller — the reference standard).
    Centered = balanced."""
    W, H = canvas_for(mark)
    frac = safe_fraction_for(mark)
    ax0, ay0, ax1, ay1 = art
    aw, ah = max(ax1 - ax0, 1e-6), max(ay1 - ay0, 1e-6)
    return min(frac * W / aw, frac * H / ah)


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
        cw, ch = canvas_for(mark)
        art = ctx.model.viewbox or (0.0, 0.0, float(cw), float(ch))
    if with_background:
        return _render_with_bg(ctx, vroot, art, mark, bg)
    return _render_transparent(ctx, vroot, art)
