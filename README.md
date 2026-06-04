# Logo Package Engine (v1)

A headless web tool that turns **one primary logo** (`.ai` + `.eps`) into a
complete, correctly-formatted delivery package — every color treatment, every
format, every size, plus the transparent set — and returns it as a `.zip`.

> Upload → mark the icon → confirm colors → download. No database, no login,
> no integrations. See [`BUILD_SPEC.md`](./BUILD_SPEC.md) for the full contract.

```
.ai + .eps  ──▶  working SVG  ──▶  [icon box] + [confirmed colors]  ──▶  ZIP
              (pdf2svg)          (centroid select)  (treatment engine)   (51 files
                                                                          + .ai/.eps)
```

## Architecture

| Layer | Stack | Role |
|-------|-------|------|
| Frontend | React + Vite + Tailwind | Renders the working **SVG as true vector**; icon box overlay mapped to SVG user space (§7.2). |
| Backend  | Python + FastAPI | `POST /ingest`, `POST /generate`, `GET /health`. Stateless — one temp dir per job, deleted on completion. |
| Vector toolchain | pdf2svg · svgelements · lxml · cairosvg · rsvg-convert | `.ai`→SVG, geometry, recoloring, raster/PDF export. |

The engine **operates in vector space throughout** — it never crops a preview
or pixel-samples a gradient (the §8 hard rules). `svgelements` provides geometry
(bbox/centroid with transforms resolved); `lxml` owns the fill model so
gradients survive as first-class objects.

### Backend modules (`backend/app/`)

| Module | Responsibility | Spec |
|--------|----------------|------|
| `ingest.py` | `.ai`(PDF) → working SVG, gradient defs preserved | §7.1 |
| `svg_model.py` / `svgutil.py` | path model: geometry ↔ fill, CSS-class resolution | §7.3 |
| `selection.py` | centroid-in-box icon select, wordmark = remainder, named layers | §7.3 |
| `colors.py` | brand ranking (dark=A, vivid=B), scope classifier → manual | §6.1, §7.4, §9 |
| `gradients.py` | rebuild a **canvas-scale** gradient from source stops/direction | §7.5 |
| `treatments.py` | the §6 recipes as SVG transforms + placement | §6, §7.6 |
| `exporters.py` | SVG / PNG@1080 / JPG 1920×1080 / vector PDF | §7.7 |
| `packager.py` | exact §5.1 tree + naming → zip; `.ai`/`.eps` pass-through | §5, §7.8 |
| `pipeline.py` / `main.py` | orchestration + FastAPI surface | §2, §3 |

## Quick start

```bash
# 1. Install the toolchain (system binaries + Python venv + npm deps)
./scripts/setup.sh

# 2. Run the backend (http://localhost:8000)
.venv/bin/uvicorn app.main:app --app-dir backend --reload

# 3. Run the frontend (http://localhost:5173, proxies the API)
cd frontend && npm run dev
```

System packages (installed by `scripts/setup.sh`): `pdf2svg`,
`librsvg2-bin` (rsvg-convert), `poppler-utils` (pdftocairo), `libcairo2`.

### Single-origin production build

`npm run build` in `frontend/` emits `frontend/dist/`, which `main.py` mounts at
`/`. Then `uvicorn app.main:app` serves the UI and API from one origin.

## Deploy (Docker / Render)

The engine shells out to native binaries (`pdf2svg`, `rsvg-convert`, `cairo`),
so it needs a **container host**, not a serverless runtime like Vercel. The
included `Dockerfile` is a multi-stage build (Vite frontend → FastAPI backend +
toolchain) that serves UI **and** API from one container.

```bash
docker build -t logo-engine .
docker run -p 8000:8000 logo-engine     # http://localhost:8000
```

**Render (one-click):** the repo ships a `render.yaml` Blueprint. In Render →
*New → Blueprint* → connect this repo; it builds the `Dockerfile` and runs a
single web service with a `/health` check. Render injects `$PORT`, which the
container honors. (Free plan sleeps when idle; bump to `starter` for always-on.)
Any Docker host works the same way — Railway, Fly.io, Cloud Run, a VPS.

## The CSR flow (§3)

1. **Brand name** — defaults to the `.ai` filename.
2. **Upload** `.ai` + `.eps`. Backend converts `.ai`→SVG and returns it.
3. **Mark the icon** — drag one box on the live vector preview (or confirm a
   detected named layer). Icon = paths whose centroid is inside the box;
   **wordmark = every other path** (no second drag).
4. **Confirm colors** — detected brand colors/gradient appear as swatches;
   remove a stray before it propagates into 50+ files.
5. **Generate** — download the `.zip`.

## Output package (§5.1)

```
[Brand] Files/
├─ [Brand].ai · [Brand].eps        ← pass-through, untouched
├─ JPG/  Icon 01–05 · Logo 01–05   (1920×1080, with background)
├─ PDF/  Icon 01–05 · Logo 01–05
├─ SVG/  Icon 01–05 · Logo 01–05
└─ Transparent/                    (edge-to-edge, no background)
   ├─ PNG/  Icon 01–03 · Logo 01–04   (1080px logical, exported @2× → 2160px)
   ├─ SVG/  Icon 01–03 · Logo 01–04
   └─ PDF/  Icon 01–03 · Logo 01–04
```

51 generated files + the two pass-through originals.

**Raster quality:** JPG/PNG are exported at **@2×** density (JPG 3840×2160, PNG
2160px wide) at JPEG quality 95; SVG/PDF stay vector. Tune with
`LOGO_EXPORT_SCALE` (default `2`) and `LOGO_JPG_QUALITY` (default `95`).

**Real `.ai` robustness:** PDF/Illustrator exports often include a full-page
background rect and pt→px scaling. The engine detects and excludes page/
background elements from the artwork, so the logo is centered (not rendered tiny
in a corner), colors aren't polluted by the page, and the icon set isn't blanked.

## Hard rules enforced (§8)

1. Vector space only — no preview cropping. 2. Gradients **read** from defs,
never pixel-sampled. 3. Whole-path centroid selection — no clipping. 4. Gradient
backgrounds are **rebuilt** at canvas scale (objectBoundingBox, full-bleed).
5. White knockout is fixed on any gradient background. 6. Out-of-scope inputs
are flagged **manual** and refused — no partial package. 7. RGB only. 8. `.ai`/
`.eps` pass-through only. 9. Tree/naming/dimensions match the fixture.

## Scope (§9)

**In:** solid fills (1–3 colors) and linear/radial gradients; outlined text;
separable side-by-side / stacked lockups. **Out → manual:** mesh gradients,
embedded raster, filters/shadows, in-artwork transparency, spot colors, live
text, integrated lockups. CMYK is deferred to v2 (§12).

## Tests

```bash
.venv/bin/python -m pytest      # 50 tests
```

Coverage spans selection, color/scope detection, gradient rebuild, every
treatment (pixel-verified), exporter dimensions/vector-PDF, the package
contract, and the API — each asserting the relevant §8 hard rule or §5 contract.

## Reference fixture

The ground-truth `Fire_Systems_PNG_Limited_Files.zip` (§10) was **not attached**
to this build; see [`fixtures/reference/README.md`](./fixtures/reference/README.md).
The engine is built to the spec's decoded facts and validated with the
synthetic fixtures in `fixtures/synthetic/`.
