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


def test_one_color_brand_b_falls_back_to_black():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           '<rect x="0" y="0" width="40" height="40" fill="#ec1c24"/></svg>')
    r = colors.detect(WorkingSVG.from_string(svg))
    assert r.brand_a == "#ec1c24"
    assert r.brand_b == "#000000"   # §6.1 fallback


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
