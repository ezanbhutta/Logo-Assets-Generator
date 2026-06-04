"""Regression: full-page background rects from PDF/AI exports must be excluded
from the artwork (bbox, selection, colors) so the logo isn't rendered tiny/
off-center and the icon set isn't blanked."""
from app import colors, selection
from app.svg_model import WorkingSVG

# A small logo (gold icon + dark bar) offset on a large page, behind a full-page
# white rect — mirrors pdf2svg/Illustrator output.
PAGE_LOGO = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 800" width="600" height="800">'
    '<rect x="0" y="0" width="600" height="800" fill="#ffffff"/>'          # page bg
    '<circle cx="150" cy="120" r="34" fill="#c8a04a"/>'                    # icon
    '<rect x="116" y="170" width="120" height="22" fill="#1b1b1b"/>'       # wordmark
    '</svg>'
)


def _model():
    return WorkingSVG.from_string(PAGE_LOGO)


def test_page_rect_flagged_background():
    m = _model()
    assert len(m.nodes) == 3
    assert len(m.ink_nodes) == 2                       # bg rect excluded
    assert any(n.is_background for n in m.nodes)


def test_placement_bbox_is_tight_not_page():
    m = _model()
    x0, y0, x1, y1 = m.overall_bbox()
    assert x1 - x0 < 200 and y1 - y0 < 200             # logo bbox, not 600x800 page


def test_background_color_not_a_brand_color():
    m = _model()
    r = colors.detect(m)
    assert "#ffffff" not in r.solids                   # page white isn't artwork
    assert r.brand_a == "#c8a04a"                       # the gold


def test_selection_ignores_background():
    m = _model()
    sel = selection.select_by_box(m, (110, 80, 80, 80))  # box over the icon
    assert len(sel.icon) == 1                            # the circle only
    assert len(sel.full) == 2                            # icon + wordmark, no bg rect
    for lpid in sel.full:
        assert not m.by_lpid[lpid].is_background


def test_real_logo_not_all_background():
    """Never flag everything as background — a genuinely full-bleed single mark
    must survive."""
    only_big = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                '<rect x="0" y="0" width="100" height="100" fill="#ec1c24"/></svg>')
    m = WorkingSVG.from_string(only_big)
    assert len(m.ink_nodes) == 1                         # kept, not dropped
