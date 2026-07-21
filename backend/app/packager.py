"""Package assembly (§5.1, §7.8): build the exact folder tree, copy the
pass-through `.ai`/`.eps`, and zip — top folder ``[Brand Name] Files``.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from . import masters
from .config import root_folder_name, safe_brand


class PackageBuilder:
    def __init__(self, brand: str, workdir: Path):
        # Sanitize once: brand is used for the root folder AND the pass-through
        # `.ai`/`.eps` filenames, so it must be a safe single path component.
        self.brand = safe_brand(brand)
        self.root = workdir / root_folder_name(brand)
        self.jpg = self.root / "JPEG"   # client-facing term (JPEG == JPG)
        self.pdf = self.root / "PDF"
        self.svg = self.root / "SVG"
        self.t_png = self.root / "Transparent" / "PNG"
        self.t_svg = self.root / "Transparent" / "SVG"
        self.t_pdf = self.root / "Transparent" / "PDF"
        for d in (self.jpg, self.pdf, self.svg, self.t_png, self.t_svg, self.t_pdf):
            d.mkdir(parents=True, exist_ok=True)
        # Every rendered variant's vector PDF, in package order (with-bg sets
        # first, then the transparent sets) — the pages of the master `.ai`.
        self.wb_pdfs: list[tuple[str, Path]] = []
        self.t_pdfs: list[tuple[str, Path]] = []

    def passthrough(self, ai_path: Path | None, eps_path: Path | None,
                    artboard_index: int = 0) -> None:
        """Emit the master `.ai`/`.eps` at root. The `.ai` is a multi-artboard
        master mirroring the package (owner rule): the CSR's selected original
        artboard first, then one artboard per generated variation, labeled with
        the exported names. The `.eps` stays single-artboard (the format has no
        artboard concept)."""
        masters.emit_masters(ai_path, eps_path, artboard_index,
                             self.root / f"{self.brand}.ai",
                             self.root / f"{self.brand}.eps",
                             variants=self.wb_pdfs + self.t_pdfs)

    def zip(self, out_path: Path) -> Path:
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(self.root.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(self.root.parent))
        return out_path

    def manifest(self) -> list[str]:
        return sorted(
            str(f.relative_to(self.root.parent))
            for f in self.root.rglob("*") if f.is_file()
        )
