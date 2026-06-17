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


def test_one_color_vivid_shows_brand_color_on_black():
    """Designer standard (Snoot): a VIVID one-color mark reads on black, so its
    alternate dark background is BLACK with the color kept (slot 3 = color-on-
    black) — not a deep shade. brand-B becomes black so the adaptive guard keeps
    the brand color there."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           '<rect x="0" y="0" width="40" height="40" fill="#ec1c24"/></svg>')
    r = colors.detect(WorkingSVG.from_string(svg))
    assert r.brand_a == "#ec1c24"
    assert r.brand_b == "#000000"                      # color-on-black variation
    assert colors.contrast_ratio("#ec1c24", "#000000") >= 3.0   # red reads on black


def test_tint_background_for_all_dark_brand():
    """An all-dark brand (no naturally-light color) gets a soft in-scheme TINT for
    the mono-black slot — a light BRANDED background instead of a redundant second
    plain white. The tint is a pale wash of the most vivid color; black reads on it."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
           '<rect width="60" height="60" fill="#ec1c24"/>'           # red (vivid, dark)
           '<rect x="70" width="60" height="60" fill="#112630"/></svg>')  # navy (dark)
    r = colors.detect(WorkingSVG.from_string(svg))
    assert r.tint is not None
    assert colors.luminance(r.tint) > 0.82                     # a pale wash
    assert colors.saturation(r.tint) > 0.02                    # still tinted (in-scheme), not white
    assert colors.contrast_ratio("#000000", r.tint) >= 4.5     # the black mark reads


def test_no_tint_when_brand_has_a_light_color():
    """A brand with a naturally-light color (MpCarney's gold ≈0.42 luminance)
    already supplies a light branded background, so no tint is derived — the
    mono-black slot stays plain white (proven cases untouched)."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
           '<rect width="60" height="60" fill="#dda51e"/>'           # gold (light)
           '<rect x="70" width="60" height="60" fill="#0a1622"/></svg>')  # near-black navy
    r = colors.detect(WorkingSVG.from_string(svg))
    assert r.tint is None


def test_no_tint_for_one_color_brand():
    """A single-color brand's set is already rich (color-on-black), so no tint."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           '<rect width="40" height="40" fill="#ec1c24"/></svg>')
    assert colors.detect(WorkingSVG.from_string(svg)).tint is None


def test_one_color_dark_keeps_shade_fallback():
    """A DARK one-color mark won't read on black, so it keeps the in-scheme deep
    shade as its alternate background (white reads there)."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           '<rect x="0" y="0" width="40" height="40" fill="#0b1f3a"/></svg>')  # dark navy
    r = colors.detect(WorkingSVG.from_string(svg))
    assert r.brand_a == "#0b1f3a"
    assert r.brand_b not in ("#000000", "#0b1f3a")     # a shade, not black/itself
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
