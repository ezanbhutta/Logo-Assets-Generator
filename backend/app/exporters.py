"""Format exporters (§7.7).

* SVG  — write the variant SVG verbatim (vector, gradients intact).
* PNG  — transparent set, 1080px wide, height proportional, alpha preserved.
* JPG  — with-bg, 1920×1080, flattened to RGB.
* PDF  — vector via ``rsvg-convert -f pdf`` (cairosvg fallback); gradients kept.
"""
from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import cairosvg
from PIL import Image

from .config import CANVAS_W, CANVAS_H, PNG_WIDTH

_RSVG = shutil.which("rsvg-convert")


def write_svg(svg_text: str, path: Path) -> None:
    path.write_text(svg_text, encoding="utf-8")


def write_png_transparent(svg_text: str, path: Path, width: int = PNG_WIDTH) -> None:
    """Rasterize to PNG at `width`px, proportional height, alpha preserved."""
    cairosvg.svg2png(bytestring=svg_text.encode("utf-8"),
                     write_to=str(path), output_width=width)


def write_jpg(svg_text: str, path: Path,
              width: int = CANVAS_W, height: int = CANVAS_H) -> None:
    """Rasterize the with-bg SVG at 1920×1080, flatten onto white, save JPG."""
    png_bytes = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"),
                                 output_width=width, output_height=height)
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    flat = Image.new("RGB", img.size, (255, 255, 255))
    flat.paste(img, mask=img.split()[3])
    flat.save(path, "JPEG", quality=92)


def write_pdf(svg_text: str, path: Path) -> None:
    """SVG -> vector PDF. Prefer rsvg-convert; fall back to cairosvg."""
    data = svg_text.encode("utf-8")
    if _RSVG:
        try:
            subprocess.run([_RSVG, "-f", "pdf", "-o", str(path)],
                           input=data, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            return
        except subprocess.CalledProcessError:
            pass
    cairosvg.svg2pdf(bytestring=data, write_to=str(path))


def pdf_is_vector(path: Path) -> bool:
    """True if the PDF carries no raster image XObject (vector throughout).
    Used by acceptance tests (§10 c/d)."""
    raw = path.read_bytes()
    return b"/Subtype/Image" not in raw and b"/Subtype /Image" not in raw
