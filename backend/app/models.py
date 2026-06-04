"""API request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ArtboardInfo(BaseModel):
    index: int
    label: str                       # "Artboard 1", ...
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


class IngestResponse(BaseModel):
    job_id: str
    brand: str
    converter: str
    artboard_count: int
    # When >1, the CSR MUST clarify which artboard is the primary logo before
    # generating. `primary_index` is the engine's suggestion.
    primary_index: int
    artboards: list[ArtboardInfo]


class GenerateRequestBody(BaseModel):
    job_id: str
    brand: str
    artboard: int = 0                # which artboard/page is the primary logo
    # Selection box in SVG USER-SPACE coordinates [x, y, w, h] (§7.2). Null ->
    # icon optional: logo-only unless named layers exist.
    selection_box: list[float] | None = Field(default=None, min_length=4, max_length=4)
    removed_colors: list[str] = []   # CSR-removed strays (hex)
    brand_a: str | None = None       # confirmed palette overrides
    brand_b: str | None = None


class HealthResponse(BaseModel):
    status: str
    toolchain: dict[str, bool]
