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


def emit_masters(src_ai: Path | None, src_eps: Path | None, page_index: int,
                 ai_dest: Path, eps_dest: Path) -> None:
    """Write the master ``.ai``/``.eps`` into place.

    * Multi-artboard source ``.ai`` → carve out only ``page_index`` for both
      masters (the ``.eps`` is re-rendered from that page so it can't smuggle the
      other artboards back in).
    * Single-artboard or non-PDF source → pass the uploads through untouched
      (preserves a native single ``.ai``; honors "only the selected artboard"
      trivially — there is only one)."""
    multipage = bool(src_ai and src_ai.exists() and _is_multipage_pdf(src_ai))

    if src_ai and src_ai.exists():
        if not (multipage and single_artboard_ai(src_ai, page_index, ai_dest)):
            shutil.copy2(src_ai, ai_dest)

    if src_eps and src_eps.exists():
        if not (multipage and single_artboard_eps(src_ai, page_index, eps_dest)):
            shutil.copy2(src_eps, eps_dest)
