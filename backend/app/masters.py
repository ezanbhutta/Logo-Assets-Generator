"""Single-artboard masters (§4, owner override).

The delivered ``.ai``/``.eps`` carry ONLY the artboard the CSR picked as the
primary logo — not every artboard in the uploaded file.

A PDF-compatible ``.ai`` stores each artboard as a PDF page *and* a whole-
document native (PGF) copy referenced from each page's ``/PieceInfo``. When
Illustrator re-opens an ``.ai`` it reads that native blob, so simply extracting
one PDF page is not enough — Adobe would rebuild every artboard. We extract the
chosen page **and drop the native blob**, so Adobe apps honor the single
artboard, rebuilding it from the page's editable vectors. The ``.eps`` is
re-rendered from the same page with ``pdftops``.

Single-artboard or non-PDF inputs are passed through untouched — there is
nothing to carve, and an already-native single ``.ai`` stays fully native.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .ingest import _is_pdf, page_count

_PDFTOPS = shutil.which("pdftops")

# Page entries that tie a single page back to the multi-artboard document — the
# native Illustrator artwork (PGF), the page thumbnail, and per-page metadata.
# Dropping them is what makes Adobe treat the extract as one standalone artboard.
_STRIP_KEYS = ("/PieceInfo", "/Thumb", "/Metadata", "/B")


def _is_multipage_pdf(src: Path) -> bool:
    try:
        return _is_pdf(src.read_bytes()) and page_count(src) > 1
    except Exception:
        return False


def single_artboard_ai(src_ai: Path, page_index: int, dest: Path) -> bool:
    """Write ``dest`` = only page ``page_index`` of ``src_ai`` with the native
    multi-artboard data stripped. Returns True on success."""
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import NameObject
    except Exception:
        return False
    try:
        reader = PdfReader(str(src_ai))
        if page_index < 0 or page_index >= len(reader.pages):
            return False
        page = reader.pages[page_index]
        for key in _STRIP_KEYS:
            if key in page:
                del page[NameObject(key)]
        writer = PdfWriter()
        writer.add_page(page)            # clones only the (now-stripped) page tree
        with open(dest, "wb") as fh:
            writer.write(fh)
        return dest.exists() and dest.stat().st_size > 0
    except Exception:
        return False


def single_artboard_eps(src_ai: Path, page_index: int, dest: Path) -> bool:
    """Render page ``page_index`` of ``src_ai`` to a single-artboard EPS. Returns
    True on success (needs ``pdftops``)."""
    if not _PDFTOPS:
        return False
    p = str(page_index + 1)
    try:
        subprocess.run([_PDFTOPS, "-eps", "-f", p, "-l", p, str(src_ai), str(dest)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return dest.exists() and dest.stat().st_size > 0
    except subprocess.CalledProcessError:
        return False


def build_variations_ai(src_ai: Path | None, page_index: int,
                        variants: list[tuple[str, Path]], dest: Path) -> bool:
    """Write ``dest`` = a multi-artboard master ``.ai`` mirroring the package
    (owner rule): the ORIGINAL selected artboard first (when ``src_ai`` is a
    readable PDF, its native blob stripped), then ONE ARTBOARD PER GENERATED
    VARIATION — each merged from the variant's already-rendered vector PDF, in
    package order. Every page gets a PDF page label carrying the variation's
    exported name (``Logo 01``, ``Transparent Icon 02`` …), so the artboards
    are identifiable and ordered exactly like the exported files. Illustrator
    opens each page of a PDF-compatible ``.ai`` as an artboard. Returns True
    on success; any failure returns False so the caller can fall back."""
    if not variants:
        return False
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import NameObject
    except Exception:
        return False
    try:
        writer = PdfWriter()
        labels: list[str] = []
        if src_ai is not None:
            reader = PdfReader(str(src_ai))       # unreadable -> except -> fallback
            if not (0 <= page_index < len(reader.pages)):
                page_index = 0
            page = reader.pages[page_index]
            for key in _STRIP_KEYS:
                if key in page:
                    del page[NameObject(key)]
            writer.add_page(page)
            labels.append("Original")
        for name, pdf in variants:
            try:
                vreader = PdfReader(str(pdf))
            except Exception:
                continue                          # skip one bad variant, keep the rest
            for pg in vreader.pages:
                writer.add_page(pg)
                labels.append(name)
        if not labels or labels == ["Original"]:
            return False                          # no variant made it in
        for i, name in enumerate(labels):
            try:
                writer.set_page_label(i, i, prefix=name)
            except Exception:
                pass                              # labels are best-effort
        with open(dest, "wb") as fh:
            writer.write(fh)
        return dest.exists() and dest.stat().st_size > 0
    except Exception:
        return False


def emit_masters(src_ai: Path | None, src_eps: Path | None, page_index: int,
                 ai_dest: Path, eps_dest: Path,
                 variants: list[tuple[str, Path]] | None = None) -> None:
    """Write the master ``.ai``/``.eps`` into place.

    * ``.ai`` — a MULTI-ARTBOARD master mirroring the package (owner rule): the
      original selected artboard first, then one artboard per generated
      variation, pages labeled with the exported names. Falls back to the old
      behavior when the variations master can't be built (no variants, corrupt
      source): multi-artboard source → carve only ``page_index``; single/non-PDF
      source → untouched copy. With no uploaded ``.ai`` at all, a variations-only
      master is still emitted — the package always carries a master.
    * ``.eps`` — single-page format (no artboard concept): re-rendered from the
      selected page of a multipage source, else copied untouched."""
    src_bytes_pdf = bool(src_ai and src_ai.exists() and _is_pdf(src_ai.read_bytes()))
    made_ai = build_variations_ai(src_ai if src_bytes_pdf else None,
                                  page_index, variants or [], ai_dest)

    multipage = bool(src_ai and src_ai.exists() and _is_multipage_pdf(src_ai))
    if not made_ai and src_ai and src_ai.exists():
        if not (multipage and single_artboard_ai(src_ai, page_index, ai_dest)):
            shutil.copy2(src_ai, ai_dest)

    if src_eps and src_eps.exists():
        if not (multipage and single_artboard_eps(src_ai, page_index, eps_dest)):
            shutil.copy2(src_eps, eps_dest)
