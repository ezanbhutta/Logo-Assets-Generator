"""API surface (§2/§3): /health, /ingest, /generate, manual-flag refusal."""
import io
import os
import tempfile
import zipfile

import pytest

os.environ.setdefault("LOGO_WORK_ROOT", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
FAKE_AI = b"%PDF-1.5\n% fake pdf-compatible ai\n"
FAKE_EPS = b"%!PS-Adobe-3.0 EPSF-3.0\n"


def _ingest(svg_bytes, name="Brand X.svg", eps=True):
    files = {"ai": (name, svg_bytes, "image/svg+xml")}
    if eps:
        files["eps"] = ("Brand X.eps", FAKE_EPS, "application/postscript")
    return client.post("/ingest", files=files)


def test_health_reports_toolchain():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["toolchain"]["pdf2svg"] is True


def test_ingest_brand_defaults_to_filename(solid_svg):
    r = _ingest(solid_svg, name="Fire Systems.svg")
    assert r.status_code == 200
    assert r.json()["brand"] == "Fire Systems"      # §3.1


def test_ingest_detects_colors_and_layers(solid_svg):
    j = _ingest(solid_svg).json()
    assert j["classification"] == "solid"
    assert j["brand_a"] == "#112630" and j["brand_b"] == "#ec1c24"
    assert j["named_selection"]["source"] == "named-layers"


def test_generate_returns_zip_with_full_tree(solid_svg):
    j = _ingest(solid_svg).json()
    g = client.post("/generate", json={
        "job_id": j["job_id"], "brand": j["brand"],
        "selection_box": [10, 5, 150, 150]})
    assert g.status_code == 200
    assert g.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(g.content)).namelist()
    assert len(names) == 51 + 2                      # variants + .ai + .eps
    assert any(n.endswith("/JPG/Logo 05.jpg") for n in names)


def test_generate_cleans_job_dir(solid_svg):
    from app.main import WORK_ROOT
    j = _ingest(solid_svg).json()
    client.post("/generate", json={"job_id": j["job_id"], "brand": j["brand"],
                                   "selection_box": [10, 5, 150, 150]})
    assert not (WORK_ROOT / j["job_id"]).exists()    # temp dir removed (§2/§7.8)


def test_manual_flag_returns_422(oos_svg):
    j = _ingest(oos_svg, name="bad.svg").json()
    assert j["supported"] is False
    g = client.post("/generate", json={"job_id": j["job_id"], "brand": "Bad",
                                       "selection_box": [10, 5, 150, 150]})
    assert g.status_code == 422
    assert g.json()["detail"]["error"] == "manual_required"


def test_non_pdf_ai_rejected():
    r = _ingest(b"\x00not a pdf or svg", name="bad.ai", eps=False)
    assert r.status_code == 422


def test_unknown_job_id_404():
    g = client.post("/generate", json={
        "job_id": "00000000-0000-0000-0000-000000000000", "brand": "X",
        "selection_box": [0, 0, 10, 10]})
    assert g.status_code == 404


def test_bad_job_id_400():
    g = client.post("/generate", json={"job_id": "../etc", "brand": "X",
                                       "selection_box": [0, 0, 10, 10]})
    assert g.status_code == 400
