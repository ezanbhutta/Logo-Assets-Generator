"""Shared test fixtures and rasterize/sample helpers."""
import io
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

FIXTURES = ROOT / "fixtures" / "synthetic"
ICON_BOX = (10, 5, 150, 150)   # selection box around the flame, user space


@pytest.fixture
def solid_svg() -> bytes:
    return (FIXTURES / "fire_systems.svg").read_bytes()


@pytest.fixture
def gradient_svg() -> bytes:
    return (FIXTURES / "fire_gradient.svg").read_bytes()


@pytest.fixture
def oos_svg() -> bytes:
    return (FIXTURES / "out_of_scope_text.svg").read_bytes()


@pytest.fixture
def solid_model(solid_svg):
    from app.svg_model import WorkingSVG
    return WorkingSVG.from_string(solid_svg)


@pytest.fixture
def gradient_model(gradient_svg):
    from app.svg_model import WorkingSVG
    return WorkingSVG.from_string(gradient_svg)


def render(svg_text: str, w: int = 1920, h: int = 1080):
    """Rasterize an SVG string to a PIL RGB(A) image for pixel assertions."""
    import cairosvg
    from PIL import Image
    png = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"),
                           output_width=w, output_height=h)
    return Image.open(io.BytesIO(png))


def near(pixel, color, tol=30) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(pixel[:3], color))
