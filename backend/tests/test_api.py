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


def _primary(j):
    """Primary artboard dict from an /ingest response."""
    return j["artboards"][j["primary_index"]]


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
    assert j["artboard_count"] == 1
    p = _primary(j)
    assert p["classification"] == "solid"
    assert p["brand_a"] == "#112630" and p["brand_b"] == "#ec1c24"
    assert p["named_selection"]["source"] == "named-layers"


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
    assert _primary(j)["supported"] is False
    g = client.post("/generate", json={"job_id": j["job_id"], "brand": "Bad",
                                       "selection_box": [10, 5, 150, 150]})
    assert g.status_code == 422
    assert g.json()["detail"]["error"] == "manual_required"


def test_multi_artboard_ingest_and_generate(tmp_path):
    """A 2-artboard .ai exposes both; generate runs against the chosen one."""
    import subprocess
    from pypdf import PdfReader, PdfWriter
    svgs = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300"><circle cx="150" cy="150" r="80" fill="#ec1c24"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300"><rect x="40" y="120" width="220" height="60" fill="#112630"/></svg>',
    ]
    writer = PdfWriter()
    for i, s in enumerate(svgs):
        p = tmp_path / f"p{i}.pdf"
        subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(p)], input=s.encode(), check=True)
        for page in PdfReader(str(p)).pages:
            writer.add_page(page)
    ai = tmp_path / "multi.ai"
    with open(ai, "wb") as f:
        writer.write(f)

    j = client.post("/ingest", files={"ai": ("Multi.ai", ai.read_bytes(),
                                              "application/illustrator")}).json()
    assert j["artboard_count"] == 2
    assert len(j["artboards"]) == 2
    g = client.post("/generate", json={"job_id": j["job_id"], "brand": "Multi",
                                       "artboard": 1, "selection_box": None})
    assert g.status_code == 200
    assert g.headers["content-type"] == "application/zip"


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
