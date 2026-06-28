"""API request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ArtboardInfo(BaseModel):
    index: int                       # GLOBAL index across all uploaded files
    label: str                       # "Artboard 1", ...
    file_index: int = 0              # which uploaded file this artboard came from
    file_name: str = ""              # that file's name (for grouping in the chooser)
    page: int = 1                    # 1-based page within its file
    working_svg: str                 # lpid-tagged; the frontend renders this live
    viewbox: list[float]
    classification: str              # solid | gradient | manual
    supported: bool
    reasons: list[str] = []          # out-of-scope reasons when manual
    is_gradient: bool
    swatches: list[dict] = []
    brand_a: str
    brand_b: str
    named_selection: dict | None = None
    suggestion: dict | None = None   # auto-detected {logo_box, icon_box, note, excluded}


class IngestResponse(BaseModel):
    job_id: str
    brand: str
    converter: str
    artboard_count: int
    # When >1, the CSR MUST clarify which artboard is the primary logo before
    # generating. `primary_index` is the engine's suggestion (global index).
    primary_index: int
    files: list[str] = []            # uploaded file names, in order
    artboards: list[ArtboardInfo]


class GenerateRequestBody(BaseModel):
    job_id: str
    brand: str
    # The CSR tags artboards: one is the Logo lockup, one is the Icon (they may be
    # on different artboards or even different uploaded files). GLOBAL indices.
    logo_artboard: int = 0
    icon_artboard: int | None = None  # None -> the icon comes from the logo artboard
    # Boxes are SVG USER-SPACE coordinates [x, y, w, h] (§7.2), each within its
    # own artboard. logo_box carves the logo out of a brand-sheet (null -> whole
    # artwork); icon_box marks the icon within the icon artboard (null -> whole).
    logo_box: list[float] | None = Field(default=None, min_length=4, max_length=4)
    icon_box: list[float] | None = Field(default=None, min_length=4, max_length=4)
    # Back-compat aliases (single-artboard flow): `artboard` == logo_artboard,
    # `selection_box` == icon_box within the logo artboard.
    artboard: int | None = None
    selection_box: list[float] | None = Field(default=None, min_length=4, max_length=4)
    removed_colors: list[str] = []   # CSR-removed strays (hex)
    brand_a: str | None = None       # confirmed palette overrides
    brand_b: str | None = None


class SegmentRequestBody(BaseModel):
    job_id: str
    artboard: int = 0                # which artboard/page to read


class SegmentResponse(BaseModel):
    # logo/icon boxes in SVG user space [x, y, w, h] (null -> whole artwork / no icon).
    logo_box: list[float] | None = None
    icon_box: list[float] | None = None
    note: str = ""
    source: str = "none"             # 'ai' | 'geometry' | 'none'


class HealthResponse(BaseModel):
    status: str
    toolchain: dict[str, bool]
