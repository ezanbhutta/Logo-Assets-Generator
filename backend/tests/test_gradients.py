"""§7.5 / §8 rule 4 — canvas-scale gradient rebuild."""
from app import colors
from app.gradients import parse_gradient, build_canvas_gradient
from app.svgutil import local_name


def _spec(gradient_model):
    defs = gradient_model.gradient_defs()
    return parse_gradient(defs["flameGrad"], defs)


def test_parse_keeps_stops_and_direction(gradient_model):
    spec = _spec(gradient_model)
    assert spec.kind == "linear"
    assert [c for _, c, _ in spec.stops] == ["#ffb000", "#ff5a00", "#ec1c24"]
    # diagonal source (60,18)->(110,120): both components positive.
    assert spec.direction[0] > 0 and spec.direction[1] > 0


def test_rebuild_is_objectboundingbox_full_bleed(gradient_model):
    grad = build_canvas_gradient(_spec(gradient_model), "bgGradient")
    assert local_name(grad) == "linearGradient"
    assert grad.get("gradientUnits") == "objectBoundingBox"
    # endpoints land on opposite corners of the unit box (full bleed).
    x1, y1 = float(grad.get("x1")), float(grad.get("y1"))
    x2, y2 = float(grad.get("x2")), float(grad.get("y2"))
    assert {(x1, y1), (x2, y2)} <= {(0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0)}
    assert (x1, y1) != (x2, y2)


def test_rebuild_preserves_stop_colors(gradient_model):
    grad = build_canvas_gradient(_spec(gradient_model), "bgGradient")
    stop_colors = [s.get("stop-color") for s in grad if local_name(s) == "stop"]
    assert stop_colors == ["#ffb000", "#ff5a00", "#ec1c24"]


def test_darkest_stop_is_the_red(gradient_model):
    """Of the three stops the deepest red is darkest (§6.4/05)."""
    spec = _spec(gradient_model)
    assert spec.darkest_stop() == "#ec1c24"


def test_darkest_stop_handles_rgb_percent_stops():
    """pdf2svg emits stop colors as rgb(%, %, %), not hex. darkest_stop must
    normalize before computing luminance (regression: Orova 500)."""
    from app.gradients import GradientSpec
    spec = GradientSpec(kind="radial", direction=(1, 0), stops=[
        (0.0, "rgb(60.888672%, 0%, 100%)", 1.0),
        (1.0, "rgb(87.8%, 0%, 60.3%)", 1.0),
    ])
    d = spec.darkest_stop()
    assert d.startswith("#") and len(d) == 7      # valid hex, no crash


def test_gradient_generate_from_rgb_percent(tmp_path):
    """Full generate of a gradient logo whose stops are rgb(%) (the pdf2svg
    shape) — exercises the dark-stop background treatment end to end."""
    import subprocess
    from app.pipeline import run_ingest, run_generate, GenerateRequest
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600">'
           '<defs><radialGradient id="g" cx="0.5" cy="0.4" r="0.6">'
           '<stop offset="0" stop-color="#9b00ff"/><stop offset="1" stop-color="#e0009a"/>'
           '</radialGradient></defs>'
           '<circle cx="400" cy="240" r="95" fill="url(#g)"/>'
           '<rect x="250" y="380" width="300" height="50" fill="#111"/></svg>')
    pdf = tmp_path / "l.pdf"
    subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(pdf)], input=svg.encode(), check=True)
    ai = tmp_path / "l.ai"; ai.write_bytes(pdf.read_bytes())
    summ = run_ingest(ai, tmp_path)
    pa = summ.artboards[summ.primary_index]
    assert pa.is_gradient
    res = run_generate(GenerateRequest(brand="Orova", working_svg=pa.working_svg,
                                       selection_box=(305, 145, 190, 190)), tmp_path)
    assert any("/Icon 05.jpg" in m for m in res.manifest)   # dark-stop treatment built


def test_no_pixel_sampling_used():
    """Guard against the raster trap (§8 rule 2): the gradient code path must
    not import PIL/cairosvg to reconstruct gradients."""
    import app.gradients as g
    src = g.__file__
    text = open(src).read()
    assert "PIL" not in text and "getpixel" not in text and "svg2png" not in text
