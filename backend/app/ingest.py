"""Ingest: uploaded `.ai` (PDF-compatible) -> working SVG (§7.1, §4).

The `.ai` is treated as a PDF (Illustrator "Create PDF Compatible File"). We
convert to a single SVG that preserves vector paths AND gradient defs. A raw
`.svg` is accepted directly to make the engine testable without Illustrator.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_PDF2SVG = shutil.which("pdf2svg")
_PDFTOCAIRO = shutil.which("pdftocairo")


class IngestError(RuntimeError):
    pass


@dataclass
class IngestResult:
    svg_text: str
    converter: str    # 'pdf2svg' | 'pdftocairo' | 'svg-passthrough'


def _is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-" or b"%PDF-" in data[:1024]


def _is_svg(data: bytes) -> bool:
    head = data[:512].lstrip()
    return head[:5].lower() == b"<?xml" or b"<svg" in data[:512].lower()


def page_count(source: Path) -> int:
    """Number of pages/artboards. A PDF-compatible `.ai` stores each artboard as
    a PDF page, so page count == artboard count."""
    data = source.read_bytes()
    if _is_svg(data) or not _is_pdf(data):
        return 1
    try:
        from pypdf import PdfReader
        n = len(PdfReader(str(source)).pages)
        return n if n > 0 else 1
    except Exception:
        return 1


def ingest(source: Path, workdir: Path, page: int = 1,
           out_name: str = "working.svg") -> IngestResult:
    """Convert one page/artboard of `source` (.ai/.pdf/.svg) to working SVG."""
    data = source.read_bytes()

    if _is_svg(data):
        return IngestResult(svg_text=data.decode("utf-8", "replace"),
                            converter="svg-passthrough")

    if not _is_pdf(data):
        raise IngestError(
            "The .ai is not PDF-compatible. Re-save from Illustrator with "
            "'Create PDF Compatible File' enabled (§4).")

    out = workdir / out_name
    p = str(page)

    # Primary: pdf2svg (poppler/cairo) — strong on real gradient defs (§2/M1).
    if _PDF2SVG:
        try:
            subprocess.run([_PDF2SVG, str(source), str(out), p],
                           check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE)
            if out.exists() and out.stat().st_size > 0:
                return IngestResult(svg_text=out.read_text("utf-8"),
                                    converter="pdf2svg")
        except subprocess.CalledProcessError:
            pass

    # Fallback: pdftocairo -svg (also poppler-backed).
    if _PDFTOCAIRO:
        try:
            subprocess.run([_PDFTOCAIRO, "-svg", "-f", p, "-l", p,
                            str(source), str(out)],
                           check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE)
            if out.exists() and out.stat().st_size > 0:
                return IngestResult(svg_text=out.read_text("utf-8"),
                                    converter="pdftocairo")
        except subprocess.CalledProcessError:
            pass

    raise IngestError("Could not convert the .ai/PDF to SVG. No working "
                      "converter (pdf2svg / pdftocairo) succeeded.")
