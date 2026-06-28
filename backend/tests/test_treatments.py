"""§6 / §7.5 / §7.6 — treatment recoloring, backgrounds, placement.

The with-background SOLID set is the owner's trained recipe (PACK FRESH CLUB),
built per-logo by ``recipes.build_solid``:

  01  white  · the PRIMARY logo exactly as authored (the guard never runs).
  02  dark   · the SAME logo on the darkest shade in the logo, or BLACK when it
               has none. Canvas-only: a colour that vanishes on the field lifts.
  03·04 the two brand colours as fields · the colour-SWAP pair (a flat color-B
               logo on the color-A field and vice-versa), or a mono knockout when
               the two colours would clash.
  05  white  · the one-colour BLACK monochrome.
"""
import pytest

from app import colors, selection, treatments
from app.config import CANVAS_W, CANVAS_H
from app.svg_model import WorkingSVG
from app.recipes import build_solid, GRADIENT_LOGO, TRANSPARENT_LOGO
from conftest import render, near, ICON_BOX

MID = CANVAS_H // 2


def _ctx(model):
    sel = selection.select_by_box(model, ICON_BOX)
    rep = colors.detect(model)
    return treatments.build_context(model, sel, rep), rep


def _solid(rep, mark="logo"):
    return build_solid(rep, mark)


def _bg_pixel(svg):
    return render(svg).convert("RGB").getpixel((20, 20))


# --- the five solid fields ---------------------------------------------------
def test_solid_logo_backgrounds(solid_model):
    """The six with-bg fields for Fire (navy #112630 + red #ec1c24): white · navy
    (the dark shade) · navy + red (the two swap fields) · white (black mono) ·
    black (white mono)."""
    ctx, rep = _ctx(solid_model)
    expect = {1: (255, 255, 255), 2: (17, 38, 48), 3: (17, 38, 48),
              4: (236, 28, 36), 5: (255, 255, 255), 6: (0, 0, 0)}
    rec = _solid(rep)
    assert len(rec) == 6
    for t in rec:
        bg = _bg_pixel(treatments.render_variant(ctx, "logo", t, True))
        assert near(bg, expect[t.index]), f"Logo {t.index} bg {bg}"


def test_primary_is_authored_colours_untouched(solid_model):
    """Slot 01 (white/primary) is the logo EXACTLY as authored — the contrast
    guard never runs on the white primary, so BOTH navy and red survive. This is
    the PACK / Aurora 'never mangle the primary' rule."""
    ctx, rep = _ctx(solid_model)
    out = treatments.render_variant(ctx, "logo", _solid(rep)[0], True)
    img = render(out).convert("RGB")
    reds = navies = 0
    for x in range(0, CANVAS_W, 3):
        for y in range(0, CANVAS_H, 12):
            p = img.getpixel((x, y))
            reds += near(p, (236, 28, 36))
            navies += near(p, (17, 38, 48), tol=40)
    assert reds > 0 and navies > 0          # both authored colours present


def test_primary_preserves_same_colour_parts_and_detail_on_white():
    """Two cases the old guard broke, both fixed by leaving the white primary
    untouched: (a) the Aurora same-colour pyramid + base bar stay their gray,
    and (b) white detail sitting on a coloured shape stays white (never flipped
    to black)."""
    gray = "#708da0"
    aurora = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200">'
              f'<path d="M150,40 L60,150 L70,150 L150,55 L230,150 L240,150 Z" fill="{gray}"/>'
              f'<path d="M60,150 L64,162 L236,162 L240,150 Z" fill="{gray}"/></svg>')
    m = WorkingSVG.from_string(aurora)
    sel = selection.select_by_box(m, (50, 30, 200, 140))
    ctx = treatments.build_context(m, sel, colors.detect(m))
    img = render(treatments.render_variant(ctx, "logo", _solid(ctx.report)[0], True)).convert("RGB")
    grays = sum(near(img.getpixel((x, y)), (112, 141, 160), tol=45)
                for x in range(int(CANVAS_W*0.35), int(CANVAS_W*0.65), 6)
                for y in range(int(CANVAS_H*0.52), int(CANVAS_H*0.60), 4))
    assert grays > 0, "same-colour base bar was erased on the white primary"

    gear = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
            '<circle cx="100" cy="100" r="60" fill="#7229ff"/>'
            '<rect x="92" y="60" width="16" height="80" fill="#ffffff"/></svg>')
    m2 = WorkingSVG.from_string(gear)
    sel2 = selection.select_by_box(m2, (38, 38, 124, 124))
    ctx2 = treatments.build_context(m2, sel2, colors.detect(m2))
    img2 = render(treatments.render_variant(ctx2, "logo", _solid(ctx2.report)[0], True)).convert("RGB")
    blacks = sum(near(img2.getpixel((x, y)), (0, 0, 0))
                 for x in range(0, CANVAS_W, 12) for y in range(0, CANVAS_H, 12))
    assert blacks == 0, "white detail on the shape was wrongly knocked to black"


# --- slot 02: the same logo on the dark field --------------------------------
def test_slot2_keep_same_on_dark_canvas_only(solid_model):
    """Slot 02 = the SAME logo on the dark field (navy here), canvas-only: the
    red icon READS on navy so it stays red; the navy wordmark vanishes on navy
    so it lifts to white. Sibling strokes are judged on the field, not each
    other (so a layered wordmark lands verbatim)."""
    ctx, rep = _ctx(solid_model)
    img = render(treatments.render_variant(ctx, "logo", _solid(rep)[1], True)).convert("RGB")
    reds = whites = 0
    for x in range(0, CANVAS_W, 4):
        p = img.getpixel((x, MID))
        reds += near(p, (236, 28, 36))
        whites += near(p, (255, 255, 255))
    assert reds > 0 and whites > 0


def test_keep_lands_layered_wordmark_verbatim():
    """A layered/offset wordmark (two sibling stroke colours, neither containing
    the other) lands on its dark field with BOTH colours intact — 'keep' never
    treats one sibling stroke as the backdrop of the other."""
    blue, yellow = "#96b6dd", "#fad15f"   # PACK FRESH CLUB's two light colours
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 120">'
           f'<path d="M20,20 H200 V60 H20 Z" fill="{blue}"/>'
           f'<path d="M30,30 H210 V70 H30 Z" fill="{yellow}"/></svg>')   # offset sibling
    m = WorkingSVG.from_string(svg)
    rep = colors.detect(m)
    sel = selection.select_by_box(m, (10, 10, 220, 80))
    ctx = treatments.build_context(m, sel, rep)
    out = treatments.render_variant(ctx, "logo", _solid(rep)[1], True)   # dark/keep
    assert _bg_pixel(out) == (0, 0, 0) or near(_bg_pixel(out), (0, 0, 0))  # black field
    # both authored colours survive on the dark field (canvas-only keeps them)
    assert blue in out and yellow in out
    assert "#ffffff" not in out.split("<rect")[1]   # nothing lifted to white


# --- slots 03/04: the two-colour swap ----------------------------------------
def test_colour_swap_is_flat_other_brand_colour(solid_model):
    """Slots 03/04 = the colour-swap pair. Navy+red harmonise, so each brand
    field carries the OTHER brand colour, FLAT: slot 03 = all-red on navy,
    slot 04 = all-navy on red. One colour, no white/black substitution."""
    ctx, rep = _ctx(solid_model)
    assert colors.colors_harmonize(rep.brand_a, rep.brand_b)
    s3 = treatments.render_variant(ctx, "logo", _solid(rep)[2], True)
    s4 = treatments.render_variant(ctx, "logo", _solid(rep)[3], True)
    img3 = render(s3).convert("RGB")
    reds3 = sum(near(img3.getpixel((x, MID)), (236, 28, 36)) for x in range(0, CANVAS_W, 4))
    assert reds3 > 0                                  # red mark on the navy field
    img4 = render(s4).convert("RGB")
    navies4 = sum(near(img4.getpixel((x, MID)), (17, 38, 48), tol=40) for x in range(0, CANVAS_W, 4))
    assert navies4 > 0                                # navy mark on the red field
    # flat = a single colour: slot 03's marks introduce no white knockout
    assert "#ffffff" not in s3.split("</rect>")[-1]


def test_colour_swap_clash_falls_back_to_mono_knockout():
    """When the two brand colours would clash on each other (both bold, little
    tonal separation — red/green), the swap falls back to the designer mono: a
    WHITE mark on the darker field, a BLACK mark on the lighter field."""
    red, green = "#e2231a", "#1ca84e"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">'
           f'<rect x="40" y="60" width="150" height="80" fill="{red}"/>'
           f'<rect x="210" y="60" width="150" height="80" fill="{green}"/></svg>')
    m = WorkingSVG.from_string(svg)
    rep = colors.detect(m)
    assert not colors.colors_harmonize(rep.brand_a, rep.brand_b)
    sel = selection.select_by_box(m, (30, 50, 350, 100))
    ctx = treatments.build_context(m, sel, rep)
    s3 = treatments.render_variant(ctx, "logo", _solid(rep)[2], True)   # darker field
    s4 = treatments.render_variant(ctx, "logo", _solid(rep)[3], True)   # lighter field
    img3, img4 = render(s3).convert("RGB"), render(s4).convert("RGB")
    whites = sum(near(img3.getpixel((x, MID)), (255, 255, 255)) for x in range(0, CANVAS_W, 4))
    blacks = sum(near(img4.getpixel((x, MID)), (0, 0, 0)) for x in range(0, CANVAS_W, 4))
    assert whites > 0, "white mark expected on the darker brand field"
    assert blacks > 0, "black mark expected on the lighter brand field"


# --- slot 05 + transparent monos ---------------------------------------------
def test_monochrome_slots_are_black_on_white_and_white_on_black(solid_model):
    """The owner ships BOTH monochromes as their own slides: 05 = black mark on
    white, 06 = white mark on black."""
    ctx, rep = _ctx(solid_model)
    s5 = treatments.render_variant(ctx, "logo", _solid(rep)[4], True)
    assert near(_bg_pixel(s5), (255, 255, 255))
    img5 = render(s5).convert("RGB")
    assert sum(near(img5.getpixel((x, MID)), (0, 0, 0)) for x in range(0, CANVAS_W, 4)) > 0
    s6 = treatments.render_variant(ctx, "logo", _solid(rep)[5], True)
    assert near(_bg_pixel(s6), (0, 0, 0))
    img6 = render(s6).convert("RGB")
    assert sum(near(img6.getpixel((x, MID)), (255, 255, 255)) for x in range(0, CANVAS_W, 4)) > 0


def test_transparent_set_ships_both_one_colour_marks(solid_model):
    """The transparent set still carries BOTH one-colour marks — white (logo 03)
    and black (logo 04) — so the package always has the full monochrome pair."""
    ctx, _ = _ctx(solid_model)
    white = treatments.render_variant(ctx, "logo", TRANSPARENT_LOGO[2], False)
    black = treatments.render_variant(ctx, "logo", TRANSPARENT_LOGO[3], False)
    assert "#ffffff" in white and "#000000" in black


# --- mascots: layer-aware in-scheme substitution still works -----------------
def test_adaptive_substitutes_in_palette_not_white_on_brand_field():
    """A 3+-colour mascot has no two-colour swap, so its brand fields use the
    LAYER-AWARE full recolor: on the brown brand field the brown body becomes the
    mascot's own cream (the nearest palette colour that reads) and the readable
    orange beak is KEPT — never an out-of-scheme white."""
    brown, cream, orange = "#5b3a1e", "#f4e9d8", "#e07020"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">'
           f'<rect x="60" y="40" width="120" height="120" fill="{brown}"/>'    # body
           f'<circle cx="120" cy="120" r="30" fill="{cream}"/>'                # belly ON body
           f'<path d="M220,60 L300,60 L260,140 Z" fill="{orange}"/></svg>')    # beak beside
    m = WorkingSVG.from_string(svg)
    rep = colors.detect(m)
    assert rep.brand_a == brown                       # darkest chromatic
    sel = selection.select_by_box(m, (50, 30, 260, 140))
    ctx = treatments.build_context(m, sel, rep)
    out = treatments.render_variant(ctx, "logo", _solid(rep)[2], True)  # brand-A (brown) field, full
    assert cream in out                               # brown body -> in-scheme cream
    assert orange in out                              # readable orange kept
    assert "#ffffff" not in out                       # no out-of-scheme white


def test_single_color_logo_stays_visible_on_its_brand_field():
    """A single-colour mark must not vanish on its own brand field — it's knocked
    out to a visible colour (the APEX case)."""
    purple = "#7a2fb0"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">'
           f'<path d="M120,90 L180,70 L240,90 L180,110 Z" fill="{purple}"/>'
           f'<rect x="150" y="170" width="100" height="40" fill="{purple}"/></svg>')
    m = WorkingSVG.from_string(svg)
    rep = colors.detect(m)
    assert rep.brand_a == purple
    sel = selection.select_by_box(m, (110, 60, 150, 70))
    ctx = treatments.build_context(m, sel, rep)
    img = render(treatments.render_variant(ctx, "icon", _solid(rep, "icon")[1], True)).convert("RGB")
    W, H = img.size
    bg = img.getpixel((20, 20))
    ink = sum(1 for x in range(0, W, 8) for y in range(0, H, 8)
              if not near(img.getpixel((x, y)), bg, tol=28))
    assert ink > 0, "single-colour icon disappeared on its own brand field"


# --- structure / placement / pruning -----------------------------------------
def test_icon_variant_uses_only_icon_paths(solid_model):
    """Icon set draws the flame only — no wordmark bars (§6.3). The icon variant
    carries 1 leaf (flame); the logo variant carries all 11."""
    import re
    ctx, rep = _ctx(solid_model)
    icon = treatments.render_variant(ctx, "icon", _solid(rep, "icon")[0], True)
    logo = treatments.render_variant(ctx, "logo", _solid(rep)[0], True)

    def leaves(svg):
        return len(re.findall(r"<(path|rect|circle|ellipse|polygon|polyline|line)\b", svg))
    assert leaves(icon) == 2     # flame(1) + bg(1)
    assert leaves(logo) == 12    # 11 + bg(1)


def test_clipped_shape_survives_subset_pruning():
    """A clip-path definition is not artwork and must never be pruned — else the
    clipped shape vanishes in the icon subset (Orova)."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
           '<defs><clipPath id="c"><circle cx="60" cy="60" r="40"/></clipPath></defs>'
           '<rect x="20" y="20" width="80" height="80" fill="#7229ff" clip-path="url(#c)"/>'
           '<rect x="150" y="150" width="30" height="30" fill="#111111"/></svg>')
    m = WorkingSVG.from_string(svg)
    assert len(m.ink_nodes) == 2          # the clipPath's <circle> is NOT artwork
    sel = selection.select_by_box(m, (15, 15, 90, 90))
    ctx = treatments.build_context(m, sel, colors.detect(m))
    out = treatments.render_variant(ctx, "icon", _solid(ctx.report, "icon")[0], True)
    img = render(out).convert("RGB")
    W, H = img.size
    bg = img.getpixel((5, 5))
    ink = sum(1 for x in range(0, W, 12) for y in range(0, H, 12)
              if not near(img.getpixel((x, y)), bg, 30))
    assert ink > 0, "clipped shape vanished — clipPath was pruned"


def test_logo_placement_60pct_of_1920x1080(solid_model):
    """LOCKED: logo artboard 1920x1080; the mark's binding side spans ~60% of the
    canvas, proportional, centered."""
    ctx, rep = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "logo", _solid(rep)[0], True)
    assert 'viewBox="0 0 1920 1080"' in svg
    img = render(svg).convert("RGB")
    ink = [(x, y) for x in range(0, CANVAS_W, 2) for y in range(0, CANVAS_H, 2)
           if not near(img.getpixel((x, y)), (255, 255, 255))]
    assert ink, "expected ink on the canvas"
    xs, ys = [p[0] for p in ink], [p[1] for p in ink]
    assert 0.57 <= (max(xs) - min(xs)) / CANVAS_W <= 0.61
    assert abs((min(xs) + max(xs)) / 2 - CANVAS_W / 2) <= 8
    assert abs((min(ys) + max(ys)) / 2 - CANVAS_H / 2) <= 8


def test_icon_artboard_is_1080_square_at_42pct(solid_model):
    """LOCKED: icon artboard 1080x1080 SQUARE; the icon scales proportionally so
    its longest side spans ~42% of the artboard, centered."""
    from app.config import ICON_SAFE_FRACTION
    ctx, rep = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "icon", _solid(rep, "icon")[0], True)
    assert 'viewBox="0 0 1080 1080"' in svg and 'width="1080"' in svg and 'height="1080"' in svg
    img = render(svg).convert("RGB")
    assert img.size == (1080, 1080)
    ink = [(x, y) for x in range(0, 1080, 2) for y in range(0, 1080, 2)
           if not near(img.getpixel((x, y)), (255, 255, 255))]
    assert ink
    xs, ys = [p[0] for p in ink], [p[1] for p in ink]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    assert abs(max(w, h) / 1080 - ICON_SAFE_FRACTION) <= 0.025
    fx0, fy0, fx1, fy1 = ctx.model.overall_bbox(ctx.selection.icon)
    src_aspect = (fx1 - fx0) / (fy1 - fy0)
    assert abs((w / h) - src_aspect) / src_aspect <= 0.08
    assert abs((min(xs) + max(xs)) / 2 - 540) <= 8
    assert abs((min(ys) + max(ys)) / 2 - 540) <= 8


def test_transparent_has_tight_viewbox_no_bg(solid_model):
    """§5.2: transparent variants crop to the artwork, no canvas rect."""
    ctx, _ = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "icon", TRANSPARENT_LOGO[0], False)
    assert f'viewBox="0 0 {CANVAS_W} {CANVAS_H}"' not in svg
    img = render(svg, w=300, h=300)
    assert img.convert("RGBA").getpixel((1, 1))[3] == 0


def test_transparent_svg_is_zero_origin_and_edge_to_edge(solid_model):
    """Transparent SVGs use a ZERO-origin viewBox (0 0 w h), artwork edge-to-edge
    (a non-zero origin renders with white letterboxing — the Eveline case)."""
    import io
    import re
    import cairosvg
    from PIL import Image
    ctx, _ = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "logo", TRANSPARENT_LOGO[0], False)
    vb = re.search(r'viewBox="([^"]+)"', svg).group(1)
    assert vb.startswith("0 0 "), f"transparent viewBox not zero-origin: {vb}"
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=600)
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    bb = img.getbbox()
    W, H = img.size
    assert bb[0] <= 2 and bb[1] <= 2 and bb[2] >= W - 2 and bb[3] >= H - 2


# --- gradient set (unchanged designer standard) ------------------------------
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
    assert not near(tl, br, tol=20)
    whites = sum(near(img.getpixel((x, MID)), (255, 255, 255)) for x in range(0, CANVAS_W, 4))
    assert whites > 0


def test_gradient_full_color_preserves_gradient_ref(gradient_model):
    """Logo 01 keeps the artwork's own gradient (read, not pixel-sampled)."""
    sel = selection.select_by_box(gradient_model, ICON_BOX)
    rep = colors.detect(gradient_model)
    ctx = treatments.build_context(gradient_model, sel, rep)
    svg = treatments.render_variant(ctx, "logo", GRADIENT_LOGO[0], True)
    assert "url(#flameGrad)" in svg


def test_gradient_on_black_is_white_knockout(gradient_model):
    """§6.4/03 — the designer standard (Orova): on black the gradient mark goes
    WHITE knockout, not the gradient."""
    sel = selection.select_by_box(gradient_model, ICON_BOX)
    rep = colors.detect(gradient_model)
    ctx = treatments.build_context(gradient_model, sel, rep)
    svg = treatments.render_variant(ctx, "logo", GRADIENT_LOGO[2], True)
    assert "url(#flameGrad)" not in svg
    img = render(svg).convert("RGB")
    whites = sum(near(img.getpixel((x, MID)), (255, 255, 255)) for x in range(0, CANVAS_W, 4))
    assert whites > 0
