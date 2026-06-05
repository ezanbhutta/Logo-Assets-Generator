"""§6 / §7.5 / §7.6 — treatment recoloring, backgrounds, placement."""
import pytest

from app import colors, selection, treatments
from app.config import CANVAS_W, CANVAS_H
from app.svg_model import WorkingSVG
from app.recipes import (SOLID_LOGO, SOLID_ICON, GRADIENT_LOGO,
                         TRANSPARENT_LOGO, with_bg_recipes)
from conftest import render, near, ICON_BOX

MID = CANVAS_H // 2


def _ctx(model):
    sel = selection.select_by_box(model, ICON_BOX)
    rep = colors.detect(model)
    return treatments.build_context(model, sel, rep), rep


def _bg_pixel(svg):
    return render(svg).convert("RGB").getpixel((20, 20))


def test_solid_logo_backgrounds(solid_model):
    ctx, _ = _ctx(solid_model)
    expect = {1: (255, 255, 255), 2: (17, 38, 48), 3: (236, 28, 36),
              4: (255, 255, 255), 5: (0, 0, 0)}
    for t in SOLID_LOGO:
        bg = _bg_pixel(treatments.render_variant(ctx, "logo", t, True))
        assert near(bg, expect[t.index]), f"Logo {t.index} bg {bg}"


def test_split_keeps_icon_color_whitens_wordmark(solid_model):
    """§6.2/02 — on navy, icon stays red, wordmark turns white."""
    ctx, _ = _ctx(solid_model)
    img = render(treatments.render_variant(ctx, "logo", SOLID_LOGO[1], True)).convert("RGB")
    reds = whites = 0
    for x in range(0, CANVAS_W, 4):
        p = img.getpixel((x, MID))
        reds += near(p, (236, 28, 36))
        whites += near(p, (255, 255, 255))
    assert reds > 0 and whites > 0


def test_all_white_knockout(solid_model):
    """Logo 05: every fill -> white on black (§6.2/05)."""
    ctx, _ = _ctx(solid_model)
    img = render(treatments.render_variant(ctx, "logo", SOLID_LOGO[4], True)).convert("RGB")
    whites = sum(near(img.getpixel((x, MID)), (255, 255, 255)) for x in range(0, CANVAS_W, 4))
    assert whites > 0


def test_all_black_mono(solid_model):
    """Logo 04: every fill -> black on white (§6.2/04)."""
    ctx, _ = _ctx(solid_model)
    img = render(treatments.render_variant(ctx, "logo", SOLID_LOGO[3], True)).convert("RGB")
    blacks = sum(near(img.getpixel((x, MID)), (0, 0, 0)) for x in range(0, CANVAS_W, 4))
    assert blacks > 0


def test_icon_variant_uses_only_icon_paths(solid_model):
    """Icon set draws the flame only — no wordmark bars (§6.3). Structural: the
    icon variant carries 1 leaf (flame); the logo variant carries all 11."""
    import re
    ctx, _ = _ctx(solid_model)
    icon = treatments.render_variant(ctx, "icon", SOLID_ICON[0], True)
    logo = treatments.render_variant(ctx, "logo", SOLID_ICON[0], True)

    def leaves(svg):
        return len(re.findall(r"<(path|rect|circle|ellipse|polygon|polyline|line)\b", svg))
    # the with-bg rect adds 1 <rect> to each; icon = flame(1)+bg(1), logo = 11+bg(1)
    assert leaves(icon) == 2
    assert leaves(logo) == 12


def test_single_color_logo_stays_visible_on_brand_bg():
    """Contrast guard: a single-color logo on its own brand-A background must
    NOT vanish — it's knocked out to a visible color (the APEX case)."""
    purple = "#7a2fb0"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">'
           f'<path d="M120,90 L180,70 L240,90 L180,110 Z" fill="{purple}"/>'
           f'<rect x="150" y="170" width="100" height="40" fill="{purple}"/></svg>')
    m = WorkingSVG.from_string(svg)
    rep = colors.detect(m)
    assert rep.brand_a == purple
    sel = selection.select_by_box(m, (110, 60, 150, 70))
    ctx = treatments.build_context(m, sel, rep)
    # Icon 02 = brand-A (purple) background, icon "in its own color"
    img = render(treatments.render_variant(ctx, "icon", SOLID_ICON[1], True)).convert("RGB")
    bg = img.getpixel((20, 20))
    ink = sum(1 for x in range(0, CANVAS_W, 8) for y in range(0, CANVAS_H, 8)
              if not near(img.getpixel((x, y)), bg, tol=28))
    assert ink > 0, "single-color icon disappeared on its own brand background"


def test_contrast_guard_keeps_two_color_logo(solid_model):
    """The guard must NOT disturb a well-contrasting 2-color logo: Fire's red
    icon stays red on the navy brand-A background (split treatment)."""
    ctx, _ = _ctx(solid_model)
    img = render(treatments.render_variant(ctx, "logo", SOLID_LOGO[1], True)).convert("RGB")
    reds = sum(near(img.getpixel((x, MID)), (236, 28, 36)) for x in range(0, CANVAS_W, 4))
    assert reds > 0   # icon kept its red, not knocked out


def test_contrast_guard_is_layer_aware_keeps_detail_on_shape():
    """White detail sitting ON a colored shape stays white on a white canvas —
    the guard compares it to the shape beneath, not the canvas (Orova: white
    circuit on the purple gear must not flip to black)."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
           '<circle cx="100" cy="100" r="60" fill="#7229ff"/>'
           '<rect x="92" y="60" width="16" height="80" fill="#ffffff"/></svg>')
    m = WorkingSVG.from_string(svg)
    sel = selection.select_by_box(m, (38, 38, 124, 124))
    ctx = treatments.build_context(m, sel, colors.detect(m))
    out = treatments.render_variant(ctx, "logo", SOLID_LOGO[0], True)  # white bg, full
    img = render(out).convert("RGB")
    # full-color on white = purple + white detail only; nothing should be black
    blacks = sum(near(img.getpixel((x, y)), (0, 0, 0))
                 for x in range(0, CANVAS_W, 12) for y in range(0, CANVAS_H, 12))
    assert blacks == 0, "white detail on the shape was wrongly knocked to black"


def test_clipped_shape_survives_subset_pruning():
    """A clip-path definition is not artwork and must never be pruned — else the
    clipped shape (e.g. the gradient gear) vanishes in the icon subset (Orova)."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
           '<defs><clipPath id="c"><circle cx="60" cy="60" r="40"/></clipPath></defs>'
           '<rect x="20" y="20" width="80" height="80" fill="#7229ff" clip-path="url(#c)"/>'
           '<rect x="150" y="150" width="30" height="30" fill="#111111"/></svg>')
    m = WorkingSVG.from_string(svg)
    assert len(m.ink_nodes) == 2          # the clipPath's <circle> is NOT artwork
    sel = selection.select_by_box(m, (15, 15, 90, 90))   # only the clipped rect
    ctx = treatments.build_context(m, sel, colors.detect(m))
    out = treatments.render_variant(ctx, "icon", SOLID_ICON[0], True)
    img = render(out).convert("RGB")
    bg = img.getpixel((5, 5))
    ink = sum(1 for x in range(0, CANVAS_W, 12) for y in range(0, CANVAS_H, 12)
              if not near(img.getpixel((x, y)), bg, 30))
    assert ink > 0, "clipped shape vanished — clipPath was pruned"


def test_gradient_hero_white_knockout_on_rebuilt_gradient(gradient_model):
    """§6.4/02 + §8 rules 4&5: Logo 02 = white art on a full-bleed rebuilt
    gradient. Background differs corner-to-corner (gradient really spans)."""
    sel = selection.select_by_box(gradient_model, ICON_BOX)
    rep = colors.detect(gradient_model)
    ctx = treatments.build_context(gradient_model, sel, rep)
    svg = treatments.render_variant(ctx, "logo", GRADIENT_LOGO[1], True)
    assert "objectBoundingBox" in svg and 'url(#bgGradient)' in svg
    img = render(svg).convert("RGB")
    tl, br = img.getpixel((10, 10)), img.getpixel((CANVAS_W - 10, CANVAS_H - 10))
    assert not near(tl, br, tol=20)            # gradient spans the canvas
    # white knockout present in the artwork band
    whites = sum(near(img.getpixel((x, MID)), (255, 255, 255)) for x in range(0, CANVAS_W, 4))
    assert whites > 0


def test_gradient_full_color_preserves_gradient_ref(gradient_model):
    """Logo 01 keeps the artwork's own gradient (read, not pixel-sampled)."""
    sel = selection.select_by_box(gradient_model, ICON_BOX)
    rep = colors.detect(gradient_model)
    ctx = treatments.build_context(gradient_model, sel, rep)
    svg = treatments.render_variant(ctx, "logo", GRADIENT_LOGO[0], True)
    assert "url(#flameGrad)" in svg


def test_transparent_has_tight_viewbox_no_bg(solid_model):
    """§5.2: transparent variants crop to the artwork, no canvas rect."""
    ctx, _ = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "icon", TRANSPARENT_LOGO[0], False)
    assert f'viewBox="0 0 {CANVAS_W} {CANVAS_H}"' not in svg   # tight bbox, not canvas
    img = render(svg, w=300, h=300)  # has alpha, corners transparent
    assert img.convert("RGBA").getpixel((1, 1))[3] == 0


def test_transparent_svg_is_zero_origin_and_edge_to_edge(solid_model):
    """Transparent SVGs use a ZERO-origin viewBox (0 0 w h) and the artwork
    fills it edge-to-edge. A non-zero origin renders with white letterboxing in
    Finder/Illustrator (the Eveline case)."""
    import io
    import re
    import cairosvg
    from PIL import Image
    ctx, _ = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "logo", TRANSPARENT_LOGO[0], False)
    vb = re.search(r'viewBox="([^"]+)"', svg).group(1)
    assert vb.startswith("0 0 "), f"transparent viewBox not zero-origin: {vb}"
    # render at the SVG's natural aspect (proportional height — no letterboxing)
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=600)
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    bb = img.getbbox()                         # bbox of non-transparent pixels
    W, H = img.size
    # ink reaches every edge (within a couple px of antialiasing)
    assert bb[0] <= 2 and bb[1] <= 2 and bb[2] >= W - 2 and bb[3] >= H - 2


def test_placement_within_safe_margins(solid_model):
    """Artwork longest side <= ~65% of the canvas (§5.2)."""
    ctx, _ = _ctx(solid_model)
    img = render(treatments.render_variant(ctx, "logo", SOLID_LOGO[0], True)).convert("RGB")
    xs = [x for x in range(CANVAS_W) if not near(img.getpixel((x, MID)), (255, 255, 255))]
    assert xs, "expected ink on the mid line"
    width_frac = (max(xs) - min(xs)) / CANVAS_W
    assert width_frac <= 0.66
