"""Adversarial / edge-case hardening (beta-test finds): filename safety, raster
dimension limits, auto-segment scaling, and degenerate SVG structures."""
import pathlib

from app import selection
from app.config import safe_brand, root_folder_name
from app.exporters import write_png_transparent
from app.packager import PackageBuilder
from app.svg_model import WorkingSVG


# --- brand / filename safety -------------------------------------------------
def test_safe_brand_blocks_path_traversal():
    assert "/" not in safe_brand("../../../../tmp/PWNED")
    assert ".." not in safe_brand("../../etc/passwd")
    assert "\\" not in safe_brand("C:\\Windows\\System32")


def test_safe_brand_strips_bidi_and_falls_back():
    assert safe_brand("‮ evil") == "evil"      # RTL-override removed
    assert safe_brand("") == "Logo"
    assert safe_brand("   ") == "Logo"
    assert safe_brand("..") == "Logo"
    assert len(safe_brand("a" * 500)) <= 80


def test_package_root_stays_inside_workdir(tmp_path):
    b = PackageBuilder("../../../../tmp/escape", tmp_path)
    assert str(b.root.resolve()).startswith(str(tmp_path.resolve()))
    assert "Files" in root_folder_name("anything")


# --- raster dimension limits -------------------------------------------------
def test_png_export_caps_extreme_aspect(tmp_path):
    """A 4×2000 mark would imply a 2160×1,080,000 surface and crash cairo — the
    width must be reduced so the implied height stays within the raster limit."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 2000" '
           'width="4" height="2000"><rect width="4" height="2000" fill="#a33"/></svg>')
    out = tmp_path / "tall.png"
    write_png_transparent(svg, out)                  # must not raise
    from PIL import Image
    w, h = Image.open(out).size
    assert max(w, h) <= 16384 and w >= 1 and h >= 1


# --- viewBox normalization (converter coordinate-space drift) ---------------
def test_viewbox_derived_when_converter_omits_it():
    """Some poppler builds emit width/height but NO viewBox (and a px scale that
    differs host-to-host). Without a viewBox, `viewbox` used to fall back to the
    ink bbox — a different origin/aspect than the SVG the browser renders, so a
    box drawn on the mark missed it server-side. The viewBox must be derived
    from width/height so the served SVG, `viewbox`, geometry, and the browser
    all share ONE coordinate system."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1174.5" height="814.3">'
           '<rect x="800" y="180" width="100" height="150" fill="#111"/></svg>')
    m = WorkingSVG.from_string(svg)
    assert m.root.get("viewBox") == "0 0 1174.5 814.3"   # derived, not absent
    assert m.viewbox == (0.0, 0.0, 1174.5, 814.3)        # matches the SVG, not the ink bbox
    assert "viewBox" in m.serialize()                     # the preview gets it too
    # a box in that px space selects the mark (the live-failure coordinate scale)
    sel, inc = selection.select(m, logo_box=None, icon_box=(790, 170, 130, 170))
    assert inc is True and len(sel.icon) == 1


def test_viewbox_with_pt_units_is_stripped_to_numbers():
    """width/height carrying a unit (e.g. pt) still yield a numeric viewBox."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="880.91pt" height="610.75pt">'
           '<rect x="10" y="10" width="40" height="40" fill="#111"/></svg>')
    m = WorkingSVG.from_string(svg)
    assert m.root.get("viewBox") == "0 0 880.91 610.75"


def test_pt_units_do_not_rescale_geometry():
    """The live-failure root cause: a converter emits ``width="880.91pt"`` with a
    matching viewBox, and some svgelements versions convert the pt to px (x1.333)
    — a shape at user x=602 then measured as bbox x~802, 1.333x larger than the
    viewBox. The browser maps a box into viewBox units, the server compared it to
    px-scaled geometry, and a box ON the mark missed. width/height must be pinned
    to the viewBox's unitless size so geometry stays in viewBox space."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="880.91pt" height="610.75pt" '
           'viewBox="0 0 880.91 610.75">'
           '<rect x="602" y="133" width="58" height="110" fill="#111"/></svg>')
    m = WorkingSVG.from_string(svg)
    assert m.root.get("width") == "880.91" and m.root.get("height") == "610.75"
    bb = m.ink_nodes[0].bbox
    assert abs(bb[0] - 602) < 1 and abs(bb[2] - 660) < 1   # viewBox space, not ~802 px
    sel, inc = selection.select(m, logo_box=None, icon_box=(590, 120, 90, 140))
    assert inc is True and len(sel.icon) == 1              # viewBox-space box hits
def test_auto_segment_skips_huge_artboard():
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3000 3000">']
    for i in range(selection.SEG_MAX_NODES + 50):
        x, y = 10 + (i % 100) * 28, 10 + (i // 100) * 28
        parts.append(f'<rect x="{x}" y="{y}" width="8" height="8" fill="#222"/>')
    parts.append("</svg>")
    m = WorkingSVG.from_string("".join(parts))
    assert len(m.ink_nodes) > selection.SEG_MAX_NODES
    assert selection.auto_segment(m) is None         # bailed, didn't hang


# --- degenerate structures ---------------------------------------------------
def test_circular_use_does_not_hang():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" '
           'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 100">'
           '<defs><g id="a"><use xlink:href="#b"/></g>'
           '<g id="b"><use xlink:href="#a"/></g></defs>'
           '<rect x="10" y="10" width="20" height="20" fill="#111"/>'
           '<use xlink:href="#a" x="0" y="0"/></svg>')
    m = WorkingSVG.from_string(svg)                   # must terminate
    assert "<use" not in m.serialize()


def test_empty_and_single_node_art_are_safe():
    empty = WorkingSVG.from_string(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>')
    sel, inc = selection.select(empty)
    assert sel.full == [] and inc is False
    one = WorkingSVG.from_string(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect x="10" y="10" width="80" height="80" fill="#111"/></svg>')
    sel2, _ = selection.select(one, logo_box=(0, 0, 100, 100))
    assert len(sel2.full) == 1
