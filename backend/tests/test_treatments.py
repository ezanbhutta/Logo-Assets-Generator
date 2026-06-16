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


def test_adaptive_on_brand_a_keeps_red_lifts_navy_to_white(solid_model):
    """§6.2/02 adaptive — on the navy brand background, the red icon READS so it
    stays red; the navy wordmark vanishes so it lifts to white (no in-palette
    candidate clears the substitute bar). The classic designer brand-bg cut."""
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
    W, H = img.size
    bg = img.getpixel((20, 20))
    ink = sum(1 for x in range(0, W, 8) for y in range(0, H, 8)
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
    W, H = img.size
    bg = img.getpixel((5, 5))
    ink = sum(1 for x in range(0, W, 12) for y in range(0, H, 12)
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


def test_logo_placement_60pct_of_1920x1080(solid_model):
    """LOCKED: logo artboard 1920x1080; the mark's binding side spans exactly
    60% of the canvas, proportional, centered."""
    ctx, _ = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "logo", SOLID_LOGO[0], True)
    assert 'viewBox="0 0 1920 1080"' in svg
    img = render(svg).convert("RGB")
    ink = [(x, y) for x in range(0, CANVAS_W, 2) for y in range(0, CANVAS_H, 2)
           if not near(img.getpixel((x, y)), (255, 255, 255))]
    assert ink, "expected ink on the canvas"
    xs, ys = [p[0] for p in ink], [p[1] for p in ink]
    width_frac = (max(xs) - min(xs)) / CANVAS_W
    # the fire lockup is wide, so width binds: ink spans ~60% of the canvas width
    assert 0.57 <= width_frac <= 0.61
    # centered (balanced): equal margins on both axes within a small tolerance
    assert abs((min(xs) + max(xs)) / 2 - CANVAS_W / 2) <= 8
    assert abs((min(ys) + max(ys)) / 2 - CANVAS_H / 2) <= 8


def test_icon_artboard_is_1080_square_at_42pct(solid_model):
    """LOCKED: icon artboard 1080x1080 SQUARE; the icon scales proportionally
    (no stretch/skew) so its longest side spans ~42% of the artboard (icons sit
    smaller than logos — the reference standard, Pulse=44%), centered."""
    from app.config import ICON_SAFE_FRACTION
    ctx, _ = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "icon", SOLID_ICON[0], True)
    assert 'viewBox="0 0 1080 1080"' in svg and 'width="1080"' in svg and 'height="1080"' in svg
    img = render(svg).convert("RGB")
    assert img.size == (1080, 1080)
    # measure the ink bbox on the white background
    ink = [(x, y) for x in range(0, 1080, 2) for y in range(0, 1080, 2)
           if not near(img.getpixel((x, y)), (255, 255, 255))]
    assert ink
    xs, ys = [p[0] for p in ink], [p[1] for p in ink]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    # longest side ~42% of 1080 = 454 (sampling stride costs a couple px)
    assert abs(max(w, h) / 1080 - ICON_SAFE_FRACTION) <= 0.025
    # proportional: the flame's aspect ratio matches its source aspect (no skew)
    fx0, fy0, fx1, fy1 = ctx.model.overall_bbox(ctx.selection.icon)
    src_aspect = (fx1 - fx0) / (fy1 - fy0)
    assert abs((w / h) - src_aspect) / src_aspect <= 0.08
    # centered (balanced) on the square canvas
    assert abs((min(xs) + max(xs)) / 2 - 540) <= 8
    assert abs((min(ys) + max(ys)) / 2 - 540) <= 8


def test_adaptive_substitutes_in_palette_not_white():
    """A pro-designer recolor stays in the logo's OWN scheme: a mascot's brown
    parts on the brown brand background become the mascot's cream (the most
    similar palette color that reads) — never an out-of-scheme stark white; the
    orange that already reads is KEPT."""
    brown, cream, orange = "#5b3a1e", "#f4e9d8", "#e07020"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">'
           f'<rect x="60" y="40" width="120" height="120" fill="{brown}"/>'    # body
           f'<circle cx="120" cy="120" r="30" fill="{cream}"/>'                # belly ON body
           f'<path d="M220,60 L300,60 L260,140 Z" fill="{orange}"/></svg>')    # beak beside
    m = WorkingSVG.from_string(svg)
    rep = colors.detect(m)
    assert rep.brand_a == brown                       # darkest chromatic
    sel = selection.select_by_box(m, (50, 30, 150, 140))
    ctx = treatments.build_context(m, sel, rep)
    out = treatments.render_variant(ctx, "logo", SOLID_LOGO[1], True)  # brand-A bg
    assert cream in out                               # brown body -> in-scheme cream
    assert orange in out                              # readable orange kept, not knocked out
    assert "#ffffff" not in out                       # no out-of-scheme white introduced


def test_gradient_on_black_is_white_knockout(gradient_model):
    """§6.4/03 — the designer standard (Orova): a gradient's tone shifts across
    the mark, so on black it goes WHITE knockout, not the gradient. Logo 03 must
    carry no gradient ref and read as solid white on black."""
    sel = selection.select_by_box(gradient_model, ICON_BOX)
    rep = colors.detect(gradient_model)
    ctx = treatments.build_context(gradient_model, sel, rep)
    svg = treatments.render_variant(ctx, "logo", GRADIENT_LOGO[2], True)  # black bg
    assert "url(#flameGrad)" not in svg               # gradient NOT kept on black
    img = render(svg).convert("RGB")
    whites = sum(near(img.getpixel((x, MID)), (255, 255, 255)) for x in range(0, CANVAS_W, 4))
    assert whites > 0                                 # white knockout present on black
