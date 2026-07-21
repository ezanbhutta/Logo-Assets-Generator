"""§5.1 / §8 / §10 — end-to-end package contract and acceptance."""
import pathlib
import zipfile

import pytest

from app.pipeline import (run_ingest, run_generate, GenerateRequest, ManualFlag)


def _primary(summ):
    """The suggested primary artboard's summary."""
    return summ.artboards[summ.primary_index]


# Expected §5.1 tree (relative to the root folder), brand "Acme".
EXPECTED = {
    "JPEG": [f"{s} {i:02d}.jpg" for s in ("Icon", "Logo") for i in range(1, 7)],
    "PDF": [f"{s} {i:02d}.pdf" for s in ("Icon", "Logo") for i in range(1, 7)],
    "SVG": [f"{s} {i:02d}.svg" for s in ("Icon", "Logo") for i in range(1, 7)],
    "Transparent/PNG": [f"Icon {i:02d}.png" for i in range(1, 4)] +
                       [f"Logo {i:02d}.png" for i in range(1, 5)],
    "Transparent/SVG": [f"Icon {i:02d}.svg" for i in range(1, 4)] +
                       [f"Logo {i:02d}.svg" for i in range(1, 5)],
    "Transparent/PDF": [f"Icon {i:02d}.pdf" for i in range(1, 4)] +
                       [f"Logo {i:02d}.pdf" for i in range(1, 5)],
}


def _generate(svg_bytes, tmp_path, brand="Acme", ai=None, eps=None):
    src = tmp_path / "in.svg"
    src.write_bytes(svg_bytes)
    summ = run_ingest(src, tmp_path)
    req = GenerateRequest(brand=brand, working_svg=_primary(summ).working_svg,
                          selection_box=(10, 5, 150, 150), ai_path=ai, eps_path=eps)
    return run_generate(req, tmp_path)


def test_tree_matches_fixture_contract(solid_svg, tmp_path):
    res = _generate(solid_svg, tmp_path)
    manifest = set(res.manifest)
    for folder, names in EXPECTED.items():
        for n in names:
            assert f"Acme Files/{folder}/{n}" in manifest


def test_total_file_count(solid_svg, tmp_path):
    """57 generated variants + pass-through .ai/.eps (§5.1). With-bg is 6+6 (both
    monochromes ship as their own slides); transparent stays 4+3."""
    ai = tmp_path / "x.ai"; ai.write_bytes(b"%PDF-1.5\n% fake ai\n")
    eps = tmp_path / "x.eps"; eps.write_bytes(b"%!PS-Adobe EPSF\n")
    res = _generate(solid_svg, tmp_path, ai=ai, eps=eps)
    assert len(res.manifest) == 57 + 2


def test_passthrough_files_present_and_untouched(solid_svg, tmp_path):
    ai = tmp_path / "x.ai"; ai_bytes = b"%PDF-1.5\n% original ai bytes\n"; ai.write_bytes(ai_bytes)
    eps = tmp_path / "x.eps"; eps_bytes = b"%!PS-Adobe-3.0 EPSF-3.0\noriginal\n"; eps.write_bytes(eps_bytes)
    res = _generate(solid_svg, tmp_path, ai=ai, eps=eps)
    root = res.zip_path.parent / "Acme Files"
    assert (root / "Acme.ai").read_bytes() == ai_bytes   # §8 rule 8: untouched
    assert (root / "Acme.eps").read_bytes() == eps_bytes


def test_zip_top_folder_is_brand_files(solid_svg, tmp_path):
    res = _generate(solid_svg, tmp_path)
    with zipfile.ZipFile(res.zip_path) as zf:
        tops = {n.split("/")[0] for n in zf.namelist()}
    assert tops == {"Acme Files"}


def test_naming_zero_padded_space_before_number(solid_svg, tmp_path):
    res = _generate(solid_svg, tmp_path)
    assert "Acme Files/JPEG/Icon 01.jpg" in res.manifest
    assert "Acme Files/JPEG/Logo 06.jpg" in res.manifest


def test_no_box_generates_logo_only(tmp_path):
    """Icon is optional: with no box and no named layers, only the logo design
    files are produced (no Icon set)."""
    # a flat SVG (no named Icon/Logotype groups)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 160">'
           '<path d="M80,18 L110,92 L58,112 Z" fill="#ec1c24"/>'
           '<rect x="185" y="55" width="14" height="60" fill="#112630"/>'
           '<rect x="250" y="55" width="14" height="60" fill="#112630"/></svg>')
    src = tmp_path / "in.svg"; src.write_bytes(svg.encode())
    summ = run_ingest(src, tmp_path)
    res = run_generate(GenerateRequest(brand="Acme", working_svg=_primary(summ).working_svg,
                                       selection_box=None), tmp_path)
    assert res.include_icon is False
    assert not any("/Icon " in m for m in res.manifest)        # no icon files
    assert any("/Logo 06.jpg" in m for m in res.manifest)      # full logo set present (6 with-bg)
    assert len([m for m in res.manifest if "/Logo " in m]) == 30


def test_box_generates_both_sets(solid_svg, tmp_path):
    res = _generate(solid_svg, tmp_path)
    assert res.include_icon is True
    assert any("/Icon 01.jpg" in m for m in res.manifest)


def test_no_duplicate_slides_two_tone_dark(tmp_path):
    """The Inclement rule: a 1-chromatic-color brand (yellow icon + black
    wordmark) used to render slots 02 (dark keep) and 04 (brand-B black field)
    as the SAME full-yellow-on-black slide. No two with-bg slides may be
    identical — slot 04 becomes the two-tone: the icon keeps its yellow, the
    wordmark goes WHITE."""
    from app.pipeline import _slide_image, _looks_same
    yellow = "#f7c400"
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 240">'
           + ''.join(f'<rect x="{160 + i * 30}" y="20" width="16" height="70" fill="{yellow}"/>'
                     for i in range(3))                                  # icon: 3 yellow bars
           + ''.join(f'<rect x="{80 + i * 44}" y="150" width="30" height="40" fill="#0a0a0a"/>'
                     for i in range(6))                                  # wordmark: black glyphs
           + '</svg>')
    src = tmp_path / "in.svg"
    src.write_bytes(svg.encode())
    summ = run_ingest(src, tmp_path)
    res = run_generate(GenerateRequest(brand="Acme", working_svg=_primary(summ).working_svg,
                                       selection_box=(150, 10, 110, 90)), tmp_path)
    root = res.zip_path.parent / "Acme Files"

    logo4 = (root / "SVG" / "Logo 04.svg").read_text()
    # 04 is the two-tone: yellow icon kept + white wordmark on the dark field
    assert yellow in logo4 and "#ffffff" in logo4

    # every with-bg LOGO slide is visually unique (02 vs 04 was the pair)
    imgs = [_slide_image((root / "SVG" / f"Logo {i:02d}.svg").read_text())
            for i in range(1, 7)]
    for i in range(6):
        for j in range(i + 1, 6):
            assert not _looks_same(imgs[i], imgs[j]), \
                f"Logo {i+1:02d} and Logo {j+1:02d} read as the same slide"

    # The ICON set has no wordmark to whiten, and a 1-color yellow/black/white
    # palette has no 6th distinct composition — the original ships rather than
    # an INVENTED color: every icon-slide field stays in the logo's scheme
    # (no olive shade_of field, the owner's no-outside-colors rule).
    from conftest import render, near
    scheme = [(255, 255, 255), (0, 0, 0), (10, 10, 10), (247, 196, 0)]
    for i in range(1, 7):
        isvg = (root / "SVG" / f"Icon {i:02d}.svg").read_text()
        bg = render(isvg).convert("RGB").getpixel((10, 10))
        assert any(near(bg, c, tol=25) for c in scheme), \
            f"Icon {i:02d} field {bg} is not a color from the logo"


def test_two_tone_derived_when_icon_not_marked_in_logo(tmp_path):
    """The olive-slide regression: with the icon tagged on a SEPARATE artboard,
    the logo selection has no icon/wordmark split, and the duplicate dark slide
    fell through to the deep-shade field (olive) with black text — wrong. The
    two-tone must be DERIVED: the duplicate slot ships BLACK field · YELLOW
    icon · WHITE text even when no icon is marked within the logo artboard."""
    from app.pipeline import _slide_image, _looks_same
    from conftest import render, near
    yellow = "#f7c400"
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 240">'
           + ''.join(f'<rect x="{160 + i * 30}" y="20" width="16" height="70" fill="{yellow}"/>'
                     for i in range(3))
           + ''.join(f'<rect x="{80 + i * 44}" y="150" width="30" height="40" fill="#0a0a0a"/>'
                     for i in range(6))
           + '</svg>')
    src = tmp_path / "in.svg"
    src.write_bytes(svg.encode())
    summ = run_ingest(src, tmp_path)
    # No selection_box: mirrors the separate-icon-artboard flow (logo sel has no icon).
    res = run_generate(GenerateRequest(brand="Acme", working_svg=_primary(summ).working_svg,
                                       selection_box=None), tmp_path)
    root = res.zip_path.parent / "Acme Files"
    logo2 = (root / "SVG" / "Logo 02.svg").read_text()
    logo4 = (root / "SVG" / "Logo 04.svg").read_text()
    assert not _looks_same(_slide_image(logo2), _slide_image(logo4))
    # the replacement is the two-tone, NOT the shade field: black bg, white text
    img = render(logo4).convert("RGB")
    W, H = img.size
    assert near(img.getpixel((20, 20)), (0, 0, 0), tol=20), "field must stay black, not a shade"
    whites = yellows = 0
    for x in range(0, W, 6):
        for y in range(0, H, 6):
            p = img.getpixel((x, y))
            whites += near(p, (255, 255, 255))
            yellows += near(p, (247, 196, 0), tol=40)
    assert yellows > 0, "icon must keep its yellow"
    assert whites > 0, "wordmark must go white (two-tone), not stay dark on a shade"


def test_wordmark_box_ships_typography_set(solid_svg, tmp_path):
    """A Text box ships the WORDMARK (typography-only) set: logo-shaped with-bg
    slides (6×3) plus a 3-slot transparent set (no split — a wordmark has no
    icon inside it, the 4th slot would be a duplicate). 27 files, named
    `Wordmark NN`."""
    src = tmp_path / "in.svg"
    src.write_bytes(solid_svg)
    summ = run_ingest(src, tmp_path)
    req = GenerateRequest(brand="Acme", working_svg=_primary(summ).working_svg,
                          selection_box=(10, 5, 150, 150),      # icon: the flame
                          wordmark_box=(175, 45, 260, 80))      # text: the navy glyphs
    res = run_generate(req, tmp_path)
    assert res.include_wordmark is True
    assert "Acme Files/JPEG/Wordmark 01.jpg" in res.manifest
    assert "Acme Files/SVG/Wordmark 06.svg" in res.manifest
    assert "Acme Files/Transparent/PNG/Wordmark 03.png" in res.manifest
    assert "Acme Files/Transparent/PNG/Wordmark 04.png" not in res.manifest  # 3-slot
    assert len([m for m in res.manifest if "/Wordmark " in m]) == 27
    # the wordmark set is typography only — no red flame pixel renders (the
    # unused `.red` class may survive in the stylesheet; the flame path is gone)
    from conftest import render, near
    wm = (res.zip_path.parent / "Acme Files" / "SVG" / "Wordmark 01.svg").read_text()
    img = render(wm).convert("RGB")
    W, H = img.size
    reds = sum(near(img.getpixel((x, y)), (236, 28, 36))
               for x in range(0, W, 8) for y in range(0, H, 8))
    assert reds == 0, "flame ink leaked into the typography-only set"
    # Logo and Icon sets are untouched beside it
    assert len([m for m in res.manifest if "/Logo " in m]) == 30
    assert len([m for m in res.manifest if "/Icon " in m]) == 27


def test_wordmark_box_miss_is_loud(solid_svg, tmp_path):
    """A Text box over empty canvas refuses with box='wordmark' — never a silent
    zip with the wordmark set missing."""
    from app.selection import BoxMiss
    src = tmp_path / "in.svg"
    src.write_bytes(solid_svg)
    summ = run_ingest(src, tmp_path)
    req = GenerateRequest(brand="Acme", working_svg=_primary(summ).working_svg,
                          selection_box=(10, 5, 150, 150),
                          wordmark_box=(430, 5, 20, 20))        # empty corner
    with pytest.raises(BoxMiss) as e:
        run_generate(req, tmp_path)
    assert e.value.box == "wordmark"


def test_wordmark_stem_reserved_against_extra_lockups(solid_svg, tmp_path):
    """An extra lockup ALSO named "Wordmark" de-dupes to `Wordmark 2` instead of
    overwriting the Text-box set."""
    from app.pipeline import ExtraLockup
    src = tmp_path / "in.svg"
    src.write_bytes(solid_svg)
    summ = run_ingest(src, tmp_path)
    other = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100">'
             '<rect x="10" y="30" width="380" height="40" fill="#112630"/></svg>')
    req = GenerateRequest(brand="Acme", working_svg=_primary(summ).working_svg,
                          selection_box=(10, 5, 150, 150),
                          wordmark_box=(175, 45, 260, 80),
                          extras=[ExtraLockup("Wordmark", other)])
    res = run_generate(req, tmp_path)
    assert "Acme Files/JPEG/Wordmark 01.jpg" in res.manifest      # the Text-box set
    assert "Acme Files/JPEG/Wordmark 2 01.jpg" in res.manifest    # the lockup, de-duped


def test_extra_lockups_ship_named_sets(solid_svg, tmp_path):
    """Additional tagged artboards ship as their own NAMED lockup sets — a full
    logo-shaped set each (`Horizontal Logo 01.jpg` …), alongside Logo/Icon. The
    name is sanitized for filenames, and a name colliding with a reserved stem
    (`Logo`) is de-duped rather than overwriting the primary set."""
    from app.pipeline import ExtraLockup
    src = tmp_path / "in.svg"
    src.write_bytes(solid_svg)
    summ = run_ingest(src, tmp_path)
    horizontal = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100">'
                  '<rect x="10" y="30" width="380" height="40" fill="#112630"/></svg>')
    vertical = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 400">'
                '<rect x="30" y="10" width="40" height="380" fill="#ec1c24"/></svg>')
    req = GenerateRequest(
        brand="Acme", working_svg=_primary(summ).working_svg,
        selection_box=(10, 5, 150, 150),
        extras=[ExtraLockup("Horizontal Logo", horizontal),
                ExtraLockup("One/line: Logo?", vertical),   # unsafe chars -> sanitized
                ExtraLockup("Logo", horizontal)])           # reserved stem -> de-duped
    res = run_generate(req, tmp_path)
    # full 30-file logo-shaped set per lockup, across every folder
    assert "Acme Files/JPEG/Horizontal Logo 01.jpg" in res.manifest
    assert "Acme Files/SVG/Horizontal Logo 06.svg" in res.manifest
    assert "Acme Files/Transparent/PNG/Horizontal Logo 04.png" in res.manifest
    assert len([m for m in res.manifest if "/Horizontal Logo " in m]) == 30
    # unsafe characters stripped to a clean filename stem
    assert "Acme Files/JPEG/One line Logo 01.jpg" in res.manifest
    # "Logo" collides with the primary stem -> "Logo 2", never overwritten
    assert "Acme Files/JPEG/Logo 2 01.jpg" in res.manifest
    assert len([m for m in res.manifest if "/Logo 0" in m]) == 30   # primary intact


def test_manual_flag_refuses_no_partial_zip(oos_svg, tmp_path):
    src = tmp_path / "oos.svg"; src.write_bytes(oos_svg)
    summ = run_ingest(src, tmp_path)
    assert _primary(summ).classification == "manual"
    with pytest.raises(ManualFlag):
        run_generate(GenerateRequest(brand="Acme", working_svg=_primary(summ).working_svg,
                                     selection_box=(10, 5, 150, 150)), tmp_path)
    assert not list(tmp_path.glob("Acme Files*"))   # no partial package


def test_gradient_package_keeps_vector_and_gradient(gradient_svg, tmp_path):
    res = _generate(gradient_svg, tmp_path)
    assert res.is_gradient
    root = res.zip_path.parent / "Acme Files"
    # Acceptance (c)/(d): SVG has paths; gradient hero references a real gradient.
    hero = (root / "SVG" / "Logo 02.svg").read_text()
    assert "<path" in hero and "linearGradient" in hero and "objectBoundingBox" in hero
    full = (root / "SVG" / "Logo 01.svg").read_text()
    assert "url(#flameGrad)" in full


def _two_artboard_ai(tmp_path):
    """Build a 2-page PDF (== 2-artboard .ai) from two distinct marks."""
    import subprocess
    from pypdf import PdfReader, PdfWriter
    a = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300">'
         '<circle cx="150" cy="150" r="80" fill="#ec1c24"/></svg>')
    b = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300">'
         '<rect x="40" y="120" width="220" height="60" fill="#112630"/>'
         '<circle cx="80" cy="150" r="40" fill="#ec1c24"/></svg>')
    pdfs = []
    for i, svg in enumerate((a, b)):
        p = tmp_path / f"p{i}.pdf"
        subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(p)],
                       input=svg.encode(), check=True)
        pdfs.append(p)
    writer = PdfWriter()
    for p in pdfs:
        for page in PdfReader(str(p)).pages:
            writer.add_page(page)
    out = tmp_path / "multi.ai"
    with open(out, "wb") as f:
        writer.write(f)
    return out


def test_multiple_artboards_detected(tmp_path):
    """A multi-artboard .ai exposes every artboard so the CSR can pick the
    primary logo (not just page 1)."""
    summ = run_ingest(_two_artboard_ai(tmp_path), tmp_path)
    assert summ.artboard_count == 2
    assert all(b.ink_count >= 1 for b in summ.artboards)
    assert 0 <= summ.primary_index < 2


def test_generate_uses_chosen_artboard(tmp_path):
    summ = run_ingest(_two_artboard_ai(tmp_path), tmp_path)
    # generate from the SECOND artboard explicitly
    res = run_generate(GenerateRequest(brand="Multi",
                                       working_svg=summ.artboards[1].working_svg,
                                       selection_box=None), tmp_path)
    assert any("/Logo 01.jpg" in m for m in res.manifest)


def test_master_ai_mirrors_package_with_variation_artboards(tmp_path):
    """The delivered .ai is a MULTI-ARTBOARD master mirroring the package (owner
    rule): the CSR's selected ORIGINAL artboard first, then one artboard per
    generated variation, each page labeled with its exported name. The UNSELECTED
    source artboard is never included; the .eps stays single-artboard."""
    from pypdf import PdfReader
    src = _two_artboard_ai(tmp_path)            # real 2-page PDF (== 2-artboard .ai)
    assert len(PdfReader(str(src)).pages) == 2
    eps = tmp_path / "src.eps"; eps.write_bytes(b"%!PS-Adobe-3.0 EPSF-3.0\n% all artboards\n")
    summ = run_ingest(src, tmp_path)
    res = run_generate(GenerateRequest(
        brand="Multi", working_svg=summ.artboards[1].working_svg,
        selection_box=None, ai_path=src, eps_path=eps, artboard_index=1), tmp_path)
    root = res.zip_path.parent / "Multi Files"
    reader = PdfReader(str(root / "Multi.ai"))
    # logo-only set: 6 with-bg + 4 transparent variants, plus the original = 11
    assert len(reader.pages) == 11
    labels = list(reader.page_labels)
    assert labels[0] == "Original"
    assert "Logo 01" in labels and "Logo 06" in labels
    assert "Transparent Logo 04" in labels
    assert "/PieceInfo" not in reader.pages[0]              # native blob stripped
    eps_out = (root / "Multi.eps").read_bytes()
    assert eps_out[:4] == b"%!PS" and b"all artboards" not in eps_out  # re-rendered single board


def _blank_pdf(tmp_path, name):
    from pypdf import PdfWriter
    p = tmp_path / name
    w = PdfWriter(); w.add_blank_page(100, 100)
    with open(p, "wb") as fh:
        w.write(fh)
    return p


def test_bad_variant_pdf_is_skipped_not_fatal(tmp_path):
    """One unreadable variant PDF must be SKIPPED — never abort the whole merge
    (a lazy PdfReader can open fine and still fail at page-tree resolve). The
    good variants ship; pages and labels stay aligned."""
    import re
    from app import masters
    from pypdf import PdfReader
    good1 = _blank_pdf(tmp_path, "g1.pdf")
    good2 = _blank_pdf(tmp_path, "g2.pdf")
    # a PDF that OPENS but whose catalog points at a dangling /Pages object —
    # fails only when the page tree is resolved (the nastier failure mode)
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(re.sub(rb"(/Pages )(\d+)( 0 R)", rb"\g<1>9\g<3>",
                           _blank_pdf(tmp_path, "seed.pdf").read_bytes(), count=1))
    dest = tmp_path / "out.ai"
    ok = masters.build_variations_ai(
        None, 0, [("A 01", good1), ("B 01", bad), ("C 01", good2)], dest)
    assert ok
    r = PdfReader(str(dest))
    assert len(r.pages) == 2
    assert list(r.page_labels) == ["A 01", "C 01"]


def test_failed_master_build_leaves_no_partial_file(tmp_path):
    """A build where NO variant survives returns False and leaves neither a
    truncated master nor a temp file behind for the zip to pick up."""
    from app import masters
    bad = tmp_path / "bad.pdf"; bad.write_bytes(b"not a pdf at all")
    dest = tmp_path / "out.ai"
    assert masters.build_variations_ai(None, 0, [("X 01", bad)], dest) is False
    assert not dest.exists()
    assert not dest.with_name("out.ai.tmp").exists()


def test_non_pdf_source_still_copied_untouched(tmp_path):
    """A present-but-non-PDF source routed as the master (an .svg upload) keeps
    the documented fallback: the uploaded original is copied untouched — never
    silently reclassified as 'no source' and dropped from the package."""
    from app import masters
    svg_bytes = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="9" height="9"/></svg>'
    src = tmp_path / "s.svg"; src.write_bytes(svg_bytes)
    good = _blank_pdf(tmp_path, "v.pdf")
    masters.emit_masters(src, None, 0, tmp_path / "B.ai", tmp_path / "B.eps",
                         variants=[("Logo 01", good)])
    assert (tmp_path / "B.ai").read_bytes() == svg_bytes


def test_variations_master_built_even_without_source_ai(solid_svg, tmp_path):
    """With no uploaded .ai at all, the package still carries a master .ai built
    purely from the variation artboards, in package order, vector throughout."""
    from pypdf import PdfReader
    from app.exporters import pdf_is_vector
    res = _generate(solid_svg, tmp_path)                    # icon + logo, no ai upload
    ai = res.zip_path.parent / "Acme Files" / "Acme.ai"
    assert ai.exists()
    reader = PdfReader(str(ai))
    # icon 6 + logo 6 with-bg, then transparent icon 3 + logo 4 = 19 artboards
    assert len(reader.pages) == 19
    labels = list(reader.page_labels)
    assert labels[0] == "Icon 01" and "Logo 06" in labels
    assert labels[-1] == "Transparent Logo 04"
    assert pdf_is_vector(ai)


def test_single_artboard_source_passes_through_untouched(solid_svg, tmp_path):
    """A single-artboard (or non-multipage) source is copied verbatim — there is
    nothing to carve, and a native single .ai must stay byte-for-byte intact."""
    ai = tmp_path / "x.ai"; ai_bytes = b"%PDF-1.5\n% one-artboard ai\n"; ai.write_bytes(ai_bytes)
    eps = tmp_path / "x.eps"; eps_bytes = b"%!PS-Adobe-3.0 EPSF-3.0\nsolo\n"; eps.write_bytes(eps_bytes)
    res = _generate(solid_svg, tmp_path, ai=ai, eps=eps)
    root = res.zip_path.parent / "Acme Files"
    assert (root / "Acme.ai").read_bytes() == ai_bytes     # untouched
    assert (root / "Acme.eps").read_bytes() == eps_bytes


def test_pdf_compatible_required(tmp_path):
    """A non-PDF .ai is rejected at ingest (§4)."""
    from app.ingest import ingest, IngestError
    bad = tmp_path / "bad.ai"; bad.write_bytes(b"\x00\x01 not a pdf and not svg")
    with pytest.raises(IngestError):
        ingest(bad, tmp_path)
