"""§6.1 / §7.4 / §9 — brand ranking and scope classification."""
from app import colors
from app.svg_model import WorkingSVG


def test_brand_ranking_navy_a_red_b(solid_model):
    """brand-A = darker (navy), brand-B = vivid (red) — the canonical 2-color
    case (§6.1)."""
    r = colors.detect(solid_model)
    assert r.classification == "solid"
    assert r.brand_a == "#112630"   # navy, darker
    assert r.brand_b == "#ec1c24"   # red, vivid


def test_gradient_classification(gradient_model):
    r = colors.detect(gradient_model)
    assert r.classification == "gradient"
    assert r.is_gradient
    assert r.gradient_ids == ["flameGrad"]


def test_one_color_brand_b_is_in_scheme_shade():
    """A 1-color logo's alternate background stays IN the logo's scheme: a deep
    shade of the brand color, not plain black (owner standard)."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           '<rect x="0" y="0" width="40" height="40" fill="#ec1c24"/></svg>')
    r = colors.detect(WorkingSVG.from_string(svg))
    assert r.brand_a == "#ec1c24"
    assert r.brand_b not in ("#000000", "#ec1c24")    # a shade, not black/itself
    rr, gg, bb = (int(r.brand_b[i:i + 2], 16) for i in (1, 3, 5))
    assert rr > gg and rr > bb                         # still red-family (in-scheme)
    assert colors.contrast_ratio("#ffffff", r.brand_b) >= 4.5   # white reads on it


def test_neutral_only_logo_gets_neutral_scale_backgrounds():
    """A black/neutral-only wordmark has no chromatic brand color — the
    alternate backgrounds come from its own neutral scale (charcoal + light
    gray), not three identical black slots."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
           '<rect x="10" y="30" width="40" height="40" fill="#1d1d1b"/>'
           '<rect x="60" y="30" width="40" height="40" fill="#1d1d1b"/></svg>')
    r = colors.detect(WorkingSVG.from_string(svg))
    la, lb = colors.luminance(r.brand_a), colors.luminance(r.brand_b)
    assert 0.03 < la < 0.35                 # charcoal — darker than mid, not black
    assert lb > 0.55                        # light gray — the mark reads in its own ink
    assert colors.contrast_ratio("#1d1d1b", r.brand_b) >= 2.2


def test_best_substitute_prefers_palette_then_white():
    """The adaptive substitute: most-similar palette color that READS, else the
    designer white/black fallback (white preferred on saturated brand colors)."""
    brown, cream, orange = "#5b3a1e", "#f4e9d8", "#e07020"
    # brown failing on brown bg -> cream (in-palette, reads at 4.5+), not white
    assert colors.best_substitute(brown, brown, [brown, cream, orange]) == cream
    # nothing in-palette reads on navy -> white (designer preference)
    assert colors.best_substitute("#112630", "#112630", ["#112630"]) == "#ffffff"
    # on a light background, white fails -> black
    assert colors.best_substitute("#f4e9d8", "#f4e9d8", ["#f4e9d8"]) == "#000000"


def test_removed_stray_excluded_from_brand(solid_model):
    """A CSR-removed stray never drives a background (§3.5)."""
    r = colors.detect(solid_model, exclude={"#112630"})
    assert r.brand_a != "#112630"


def test_brand_override(solid_model):
    r = colors.detect(solid_model, brand_a_override="#001122", brand_b_override="#ff0000")
    assert r.brand_a == "#001122" and r.brand_b == "#ff0000"


def test_scope_flags_live_text(oos_svg):
    r = colors.detect(WorkingSVG.from_string(oos_svg))
    assert r.classification == "manual"
    assert any("text" in reason for reason in r.reasons)


def test_scope_flags_raster_image():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" '
           'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 100">'
           '<image x="0" y="0" width="50" height="50" xlink:href="data:foo"/></svg>')
    r = colors.detect(WorkingSVG.from_string(svg))
    assert r.classification == "manual"
    assert any("raster" in reason for reason in r.reasons)


def test_scope_flags_transparency():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           '<rect width="40" height="40" fill="#ec1c24" fill-opacity="0.5"/></svg>')
    r = colors.detect(WorkingSVG.from_string(svg))
    assert r.classification == "manual"
    assert any("transparency" in reason for reason in r.reasons)


def test_luminance_navy_is_dark_but_kept_as_brand(solid_model):
    """Navy is very dark yet chromatic, so it stays a brand color (not a
    near-black artifact)."""
    assert colors.luminance("#112630") < 0.05
    assert colors._is_brand_color("#112630")
    assert not colors._is_brand_color("#0a0a0a")  # neutral near-black -> artifact
