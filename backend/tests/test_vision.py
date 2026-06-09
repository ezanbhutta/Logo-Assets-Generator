"""AI segmentation: coordinate mapping, graceful degradation, and the /segment
endpoint's AI-first / geometry-fallback wiring. No network — the Claude call is
monkeypatched, and the no-key path is exercised directly."""
import uuid

from fastapi.testclient import TestClient

from app import main, vision
from app.selection import Suggestion

# A brand sheet: lockup (emblem + 3 letters) top-left, standalone icon top-right,
# a swatch row at the bottom — geometric auto_segment carves the lockup out.
_BENTO = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600">'
    '<circle cx="90" cy="110" r="40" fill="#7229ff"/>'
    '<rect x="170" y="95" width="24" height="30" fill="#160a33"/>'
    '<rect x="200" y="95" width="24" height="30" fill="#160a33"/>'
    '<rect x="230" y="95" width="24" height="30" fill="#160a33"/>'
    '<circle cx="700" cy="110" r="40" fill="#7229ff"/>'
    '<rect x="60" y="460" width="80" height="80" fill="#160a33"/>'
    '<rect x="180" y="460" width="80" height="80" fill="#160a33"/>'
    '<rect x="300" y="460" width="80" height="80" fill="#160a33"/>'
    '</svg>'
)


def _make_job(svg: str) -> str:
    jid = str(uuid.uuid4())
    d = main.WORK_ROOT / jid
    d.mkdir(parents=True, exist_ok=True)
    (d / "working_0.svg").write_text(svg, encoding="utf-8")
    (d / "brand.txt").write_text("Test", encoding="utf-8")
    return jid


def test_norm_to_vb_maps_and_clamps():
    vb = (0, 0, 1000, 500)
    assert vision._norm_to_vb([0.1, 0.2, 0.3, 0.4], vb) == (100.0, 100.0, 300.0, 200.0)
    # a box running past the right/bottom edge is clamped to the artboard
    assert vision._norm_to_vb([0.9, 0.0, 0.5, 1.0], vb) == (900.0, 0.0, 100.0, 500.0)
    # degenerate or malformed -> None
    assert vision._norm_to_vb([0.5, 0.5, 0.0, 0.2], vb) is None
    assert vision._norm_to_vb([1, 2, 3], vb) is None
    assert vision._norm_to_vb(None, vb) is None


def test_extract_json_is_tolerant():
    assert vision._extract_json('```json\n{"logo_box": null, "note": "x"}\n```') == {
        "logo_box": None, "note": "x"}
    assert vision._extract_json("here you go: {\"a\": 1} thanks") == {"a": 1}
    assert vision._extract_json("no json at all") is None


def test_available_and_no_key_returns_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert vision.available() is False
    assert vision.ai_segment("<svg/>", (0, 0, 100, 100)) is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert vision.available() is True


def test_segment_endpoint_falls_back_to_geometry(monkeypatch):
    monkeypatch.setattr(vision, "ai_segment", lambda *a, **k: None)  # AI unavailable
    jid = _make_job(_BENTO)
    body = TestClient(main.app).post(
        "/segment", json={"job_id": jid, "artboard": 0}).json()
    assert body["source"] == "geometry"
    assert body["logo_box"] is not None        # carved the lockup out of the bento


def test_segment_endpoint_prefers_ai(monkeypatch):
    monkeypatch.setattr(vision, "ai_segment",
                        lambda *a, **k: Suggestion(logo_box=(10, 20, 30, 40),
                                                   icon_box=None, note="AI read it."))
    jid = _make_job(_BENTO)
    body = TestClient(main.app).post(
        "/segment", json={"job_id": jid, "artboard": 0}).json()
    assert body["source"] == "ai"
    assert body["logo_box"] == [10, 20, 30, 40]
    assert body["note"] == "AI read it."


def test_segment_endpoint_rejects_bad_job():
    r = TestClient(main.app).post("/segment", json={"job_id": "not-a-uuid", "artboard": 0})
    assert r.status_code == 400
