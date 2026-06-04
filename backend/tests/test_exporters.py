"""§7.7 — exporter dimensions, vector PDF, PNG alpha."""
from PIL import Image

from app import colors, selection, treatments
from app.config import CANVAS_W, CANVAS_H, PNG_WIDTH, EXPORT_SCALE
from app.exporters import (write_svg, write_jpg, write_pdf,
                           write_png_transparent, pdf_is_vector)
from app.recipes import SOLID_LOGO, TRANSPARENT_LOGO
from conftest import ICON_BOX


def _ctx(model):
    sel = selection.select_by_box(model, ICON_BOX)
    return treatments.build_context(model, sel, colors.detect(model))


def test_jpg_is_canvas_at_export_scale_rgb(solid_model, tmp_path):
    """With-bg JPEG is the fixed 1920x1080 artboard, rasterized at @EXPORT_SCALE
    (default @2x -> 3840x2160)."""
    ctx = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "logo", SOLID_LOGO[0], True)
    out = tmp_path / "logo.jpg"
    write_jpg(svg, out)
    img = Image.open(out)
    assert img.size == (CANVAS_W * EXPORT_SCALE, CANVAS_H * EXPORT_SCALE)
    assert img.mode == "RGB"   # flattened, no alpha


def test_png_is_1080_logical_wide_at_export_scale_with_alpha(solid_model, tmp_path):
    import re
    ctx = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "icon", TRANSPARENT_LOGO[0], False)
    out = tmp_path / "icon.png"
    write_png_transparent(svg, out)
    img = Image.open(out)
    assert img.width == PNG_WIDTH * EXPORT_SCALE   # §5.2: 1080px logical @ Nx
    assert img.mode in ("RGBA", "LA")              # alpha preserved
    # height is proportional to the tight artwork bbox (viewBox aspect).
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
    expected_h = round(PNG_WIDTH * EXPORT_SCALE * vb[3] / vb[2])
    assert abs(img.height - expected_h) <= 1


def test_with_bg_pdf_is_vector(solid_model, tmp_path):
    ctx = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "logo", SOLID_LOGO[0], True)
    out = tmp_path / "logo.pdf"
    write_pdf(svg, out)
    assert out.exists() and pdf_is_vector(out)


def test_gradient_pdf_is_vector(gradient_model, tmp_path):
    """Gradient survives to PDF as vector, not a flattened raster (§8/d)."""
    sel = selection.select_by_box(gradient_model, ICON_BOX)
    ctx = treatments.build_context(gradient_model, sel, colors.detect(gradient_model))
    from app.recipes import GRADIENT_LOGO
    svg = treatments.render_variant(ctx, "logo", GRADIENT_LOGO[1], True)
    out = tmp_path / "grad.pdf"
    write_pdf(svg, out)
    assert pdf_is_vector(out)


def test_output_svg_contains_paths_not_image(solid_model, tmp_path):
    """Acceptance (c): an output SVG must contain paths, not an embedded image."""
    ctx = _ctx(solid_model)
    svg = treatments.render_variant(ctx, "logo", SOLID_LOGO[0], True)
    out = tmp_path / "logo.svg"
    write_svg(svg, out)
    text = out.read_text()
    assert "<path" in text and "<image" not in text
