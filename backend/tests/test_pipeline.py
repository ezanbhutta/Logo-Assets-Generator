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
    "JPEG": [f"{s} {i:02d}.jpg" for s in ("Icon", "Logo") for i in range(1, 6)],
    "PDF": [f"{s} {i:02d}.pdf" for s in ("Icon", "Logo") for i in range(1, 6)],
    "SVG": [f"{s} {i:02d}.svg" for s in ("Icon", "Logo") for i in range(1, 6)],
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
    """51 generated variants + pass-through .ai/.eps (§5.1)."""
    ai = tmp_path / "x.ai"; ai.write_bytes(b"%PDF-1.5\n% fake ai\n")
    eps = tmp_path / "x.eps"; eps.write_bytes(b"%!PS-Adobe EPSF\n")
    res = _generate(solid_svg, tmp_path, ai=ai, eps=eps)
    assert len(res.manifest) == 51 + 2


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
    assert "Acme Files/JPEG/Logo 05.jpg" in res.manifest


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
    assert any("/Logo 05.jpg" in m for m in res.manifest)      # full logo set present
    assert len([m for m in res.manifest if "/Logo " in m]) == 27


def test_box_generates_both_sets(solid_svg, tmp_path):
    res = _generate(solid_svg, tmp_path)
    assert res.include_icon is True
    assert any("/Icon 01.jpg" in m for m in res.manifest)


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


def test_masters_carry_only_the_selected_artboard(tmp_path):
    """The delivered .ai/.eps must contain ONLY the artboard the CSR picked — not
    every artboard in the source (§4, owner override). A 2-artboard source, with
    artboard index 1 chosen, yields single-page masters."""
    from pypdf import PdfReader
    src = _two_artboard_ai(tmp_path)            # real 2-page PDF (== 2-artboard .ai)
    assert len(PdfReader(str(src)).pages) == 2
    eps = tmp_path / "src.eps"; eps.write_bytes(b"%!PS-Adobe-3.0 EPSF-3.0\n% all artboards\n")
    summ = run_ingest(src, tmp_path)
    res = run_generate(GenerateRequest(
        brand="Multi", working_svg=summ.artboards[1].working_svg,
        selection_box=None, ai_path=src, eps_path=eps, artboard_index=1), tmp_path)
    root = res.zip_path.parent / "Multi Files"
    ai_out = root / "Multi.ai"
    assert len(PdfReader(str(ai_out)).pages) == 1           # one artboard, not two
    assert "/PieceInfo" not in PdfReader(str(ai_out)).pages[0]   # native blob stripped
    eps_out = (root / "Multi.eps").read_bytes()
    assert eps_out[:4] == b"%!PS" and b"all artboards" not in eps_out  # re-rendered single board


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
