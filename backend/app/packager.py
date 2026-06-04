"""Package assembly (§5.1, §7.8): build the exact folder tree, copy the
pass-through `.ai`/`.eps`, and zip — top folder ``[Brand Name] Files``.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from .config import root_folder_name


class PackageBuilder:
    def __init__(self, brand: str, workdir: Path):
        self.brand = brand
        self.root = workdir / root_folder_name(brand)
        self.jpg = self.root / "JPEG"   # client-facing term (JPEG == JPG)
        self.pdf = self.root / "PDF"
        self.svg = self.root / "SVG"
        self.t_png = self.root / "Transparent" / "PNG"
        self.t_svg = self.root / "Transparent" / "SVG"
        self.t_pdf = self.root / "Transparent" / "PDF"
        for d in (self.jpg, self.pdf, self.svg, self.t_png, self.t_svg, self.t_pdf):
            d.mkdir(parents=True, exist_ok=True)

    def passthrough(self, ai_path: Path | None, eps_path: Path | None) -> None:
        """Copy uploaded `.ai`/`.eps` to root, untouched (§4, §8 rule 8)."""
        if ai_path and ai_path.exists():
            shutil.copy2(ai_path, self.root / f"{self.brand}.ai")
        if eps_path and eps_path.exists():
            shutil.copy2(eps_path, self.root / f"{self.brand}.eps")

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
