"""Format exporters (§7.7).

* SVG  — write the variant SVG verbatim (vector, gradients intact).
* PNG  — transparent set, 1080px wide, height proportional, alpha preserved.
* JPG  — with-bg at the variant's own artboard size (logo 1920×1080, icon
  1080×1080), flattened to RGB.
* PDF  — vector via ``rsvg-convert -f pdf`` (cairosvg fallback); gradients kept.
"""
from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import re

import cairosvg
from PIL import Image

from .config import CANVAS_W, CANVAS_H, PNG_WIDTH, EXPORT_SCALE, JPG_QUALITY

_RSVG = shutil.which("rsvg-convert")

# Cairo rejects surfaces beyond ~32k px on a side. Keep every raster well under
# that so an extreme/degenerate aspect ratio can't blow up the render.
_MAX_RASTER_PX = 16384


def write_svg(svg_text: str, path: Path) -> None:
    path.write_text(svg_text, encoding="utf-8")


def _viewbox_wh(svg_text: str) -> tuple[float, float] | None:
    m = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', svg_text)
    if not m:
        return None
    try:
        _, _, w, h = (float(v) for v in m.group(1).replace(",", " ").split())
        return (w, h) if w > 0 and h > 0 else None
    except ValueError:
        return None


def write_png_transparent(svg_text: str, path: Path, width: int | None = None) -> None:
    """Rasterize to PNG, proportional height, alpha preserved. Defaults to the
    1080px logical width at @EXPORT_SCALE density (e.g. 2160px at @2x). The width
    is reduced if needed so a very tall logo's proportional height stays within
    cairo's surface limit (a 4×2000 mark would otherwise demand a 1,080,000px
    surface and crash)."""
    out_w = width if width is not None else PNG_WIDTH * EXPORT_SCALE
    wh = _viewbox_wh(svg_text)
    if wh:
        w, h = wh
        out_w = min(out_w, max(1, int(_MAX_RASTER_PX * w / h)))   # cap implied height
    cairosvg.svg2png(bytestring=svg_text.encode("utf-8"),
                     write_to=str(path), output_width=max(1, int(out_w)))


def write_jpg(svg_text: str, path: Path) -> None:
    """Rasterize the with-bg SVG at @EXPORT_SCALE density, flatten onto white,
    save high-quality JPG. Dimensions come from the variant's own artboard
    (logo 1920×1080, icon 1080×1080) — forcing one fixed size here would
    stretch/skew the square icon artboard."""
    wh = _viewbox_wh(svg_text)
    w, h = (wh if wh else (float(CANVAS_W), float(CANVAS_H)))
    png_bytes = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"),
                                 output_width=round(w) * EXPORT_SCALE,
                                 output_height=round(h) * EXPORT_SCALE)
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    flat = Image.new("RGB", img.size, (255, 255, 255))
    flat.paste(img, mask=img.split()[3])
    flat.save(path, "JPEG", quality=JPG_QUALITY, subsampling=0, optimize=True)


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
