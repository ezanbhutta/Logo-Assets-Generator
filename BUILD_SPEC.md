# BUILD SPEC — Logo Package Engine (v1)

> A headless web tool. A CSR uploads a logo's `.ai` + `.eps`, marks the icon on a vector preview, confirms the detected colors, and downloads a complete, correctly-formatted logo delivery package as a `.zip`. No database, no integrations, no login. Upload → zip out.

---

## 0. HOW TO USE THIS DOCUMENT (read first)

This file is the single source of truth. Build to it exactly.

1. Create a new project/repo and drop this file in the root as `BUILD_SPEC.md`.
2. **Attach the reference package** `Fire_Systems_PNG_Limited_Files.zip` to the project as the ground-truth fixture. Unzip it into `/fixtures/reference/`. Every output the engine produces must match this package's folder tree, file naming, and visual treatment. When in doubt about layout or naming, the fixture wins, not your assumptions.
3. Build **milestone by milestone (M0 → M7, §11)**. Each milestone has a gate. Do not move forward until the gate passes against the fixture.
4. The rules in **§8 (HARD RULES)** are where the easy implementation is the *wrong* one. Read §8 before writing any extraction or gradient code. If you find yourself cropping a preview image or sampling pixels, stop — you've taken the broken path.

---

## 1. WHAT WE'RE BUILDING

A stateless service that turns **one primary logo** into a full delivery package. The designer provides only the primary logo (in `.ai` + `.eps`). The engine generates every color treatment, every format, every size, and the transparent set — from that one file. The only human input beyond the upload is: (a) drag a box to mark the icon, (b) confirm the auto-detected colors.

Scope is **RGB only**. CMYK is explicitly deferred (§12).

---

## 2. ARCHITECTURE & STACK

Stateless. A request lives in a temp working directory, produces a zip, returns it, and the temp dir is deleted. Nothing persists.

**Recommended stack** (substitutions allowed *only* if they meet §8; if you substitute a converter or renderer, prove gradient fidelity against the fixture first):

- **Frontend:** React + Vite + Tailwind. The preview is the working **SVG rendered natively in the browser** (true vector, not an image). The icon-selection box is an HTML overlay mapped to SVG user-space coordinates (§7.2).
- **Backend:** Python + FastAPI. Endpoints: `POST /ingest` (file → working SVG + detected layers/colors), `POST /generate` (selection + confirmed colors → zip).
- **Vector toolchain (backend):**
  - `.ai`/PDF → working SVG: `pdf2svg` (poppler/cairo) as primary; Inkscape CLI as fallback for gradient-heavy files. **Evaluate both against the fixture in M1 and pick the one that preserves linear/radial gradients as real SVG gradient defs.**
  - SVG parsing / geometry / centroids / bounding boxes: `svgelements` (resolves transforms; gives per-element bbox + center) + `lxml` for raw tree edits.
  - SVG → PNG / JPG raster: `resvg` (most accurate modern SVG renderer, strong on gradients); `cairosvg` as fallback.
  - SVG → PDF: `rsvg-convert -f pdf` or Inkscape (vector, gradients preserved).
- **No persistence layer.** No Supabase, no auth. Temp dir per job, cleaned on completion.

---

## 3. THE CSR FLOW

1. CSR enters/confirms **Brand Name** (defaults to the `.ai` filename without extension).
2. CSR uploads `logo.ai` and `logo.eps`.
3. Backend converts `.ai` → working SVG and returns it. Frontend renders it as the live vector preview.
4. **Icon selection:** CSR clicks "Select Icon," drags one box around the icon on the preview. (If the `.ai` has named layers like `Icon`/`Logotype`, pre-highlight them and let the CSR just **confirm** — selection is the fallback, not the default.)
   - Icon = paths inside the box. **Wordmark = every other path (the remainder — no second drag).** Full logo = all paths.
5. **Color confirm:** Engine shows detected brand colors / gradient as swatches. CSR confirms or removes a stray (e.g. an off-black artifact) before it propagates into 50+ files.
6. CSR clicks **Generate**. Engine builds the package, returns a `.zip`, CSR downloads it.

---

## 4. INPUT CONTRACT

- CSR uploads **`.ai` + `.eps`**. The `.ai` must be **PDF-compatible** (Illustrator default "Create PDF Compatible File" — the fixture's `.ai` is). The engine extracts working vector by treating the `.ai` as a PDF.
- **`.ai` and `.eps` are passed through untouched** to the package root. The engine does **not** regenerate or recolor them. They carry the designer's saved color mode. One file, one mode.
- The uploaded logo is the **primary (full-color) lockup only**. All variants are generated. Do not expect a multi-artboard master.

---

## 5. OUTPUT CONTRACT

### 5.1 Folder tree (must match the fixture exactly)

```
[Brand Name] Files/
├─ [Brand Name].ai                 ← pass-through (uploaded file, untouched)
├─ [Brand Name].eps                ← pass-through (uploaded file, untouched)
├─ JPG/
│  ├─ Icon 01.jpg … Icon 05.jpg          (1920×1080, with background)
│  └─ Logo 01.jpg … Logo 05.jpg          (1920×1080, with background)
├─ PDF/
│  ├─ Icon 01.pdf … Icon 05.pdf          (1920×1080, with background)
│  └─ Logo 01.pdf … Logo 05.pdf
├─ SVG/
│  ├─ Icon 01.svg … Icon 05.svg          (1920×1080, with background)
│  └─ Logo 01.svg … Logo 05.svg
└─ Transparent/                           (edge-to-edge, no background)
   ├─ PNG/  Icon 01.png … Icon 03.png  ·  Logo 01.png … Logo 04.png
   ├─ SVG/  Icon 01.svg … Icon 03.svg  ·  Logo 01.svg … Logo 04.svg
   └─ PDF/  Icon 01.pdf … Icon 03.pdf  ·  Logo 01.pdf … Logo 04.pdf
```

- **EPS** ships as a single editable master at root only — **not** exploded per variant, **not** generated.
- **Transparent set is RGB only.**

### 5.2 Dimensions

- **With-background artboards (JPG/PDF/SVG):** exactly **1920×1080**. Logo centered, scaled to fit within safe margins (logo's longest side ≤ ~65% of the corresponding canvas dimension), aspect ratio preserved.
- **Transparent set:** **edge-to-edge** (tight bounding box of the artwork, zero padding, no background rect).
  - **PNG:** raster, **1080 px wide**, height proportional.
  - **SVG / PDF:** vector; carry the tight native bounding box (proportional by nature).

### 5.3 Naming

`Icon 01.jpg` … `Logo 05.jpg`, zero-padded two digits, space before the number. Transparent files use the same scheme inside their format subfolders. Root folder is `[Brand Name] Files`.

---

## 6. TREATMENT RECIPES

A "treatment" = a recolor + a background. Numbering maps treatment → file index. **Black is the SVG default** (a path with no fill renders black); mono variants are produced by remapping fills, not by adding a color.

### 6.1 Background auto-selection rule (handles 1, 2, or 3 brand colors)

The five with-background slots draw their backgrounds from this ordered pool: `[white, brand-A, brand-B, white, black]`, where brand-A and brand-B are the two most prominent brand colors (brand-A = the **darker**, brand-B = the more **vivid/primary**). For a **1-color** logo, brand-B falls back to `black`. For **3+ colors**, use the two most prominent for backgrounds; the rest appear only in the full-color treatment.

Treatment on each background is chosen by background **luminance**: light background → full-color or black-mono; dark/saturated background → white knockout (or the split treatment on the brand-A slot).

The 2-color case below is the canonical reference (matches the fixture: white, navy `#112630`, red `#ec1c24`, white, black).

### 6.2 SOLID logo — with background (Logo 01–05)

| # | Background | Logo treatment |
|---|-----------|----------------|
| 01 | white | full color |
| 02 | brand-A (darker, e.g. navy) | **split** — icon keeps its color, wordmark → white |
| 03 | brand-B (vivid, e.g. red) | all white |
| 04 | white | all black (mono) |
| 05 | black | all white |

### 6.3 SOLID icon — with background (Icon 01–05)

Icon has no wordmark, so "split" doesn't apply.

| # | Background | Icon treatment |
|---|-----------|----------------|
| 01 | white | full color |
| 02 | brand-A | icon in its own color |
| 03 | brand-B | white |
| 04 | white | black |
| 05 | black | white |

### 6.4 GRADIENT logo — with background (Logo 01–05)

| # | Background | Logo treatment |
|---|-----------|----------------|
| 01 | white | full color (gradient icon + dark wordmark) |
| 02 | **brand gradient, full-bleed** (rebuilt — see §7.5) | **white knockout** ← hero |
| 03 | black | white |
| 04 | white | black (mono) |
| 05 | solid sampled from the gradient's **darkest stop** | white |

### 6.5 GRADIENT icon — with background (Icon 01–05)

Same logic, icon only: `01` white/full-color · `02` brand-gradient full-bleed/white icon (hero) · `03` black/white · `04` white/black · `05` dark-stop-solid/white.

### 6.6 Transparent — LOGO (01–04)

| # | Treatment |
|---|-----------|
| 01 | full color |
| 02 | split — icon keeps color/gradient, wordmark → white |
| 03 | all white |
| 04 | all black |

### 6.7 Transparent — ICON (01–03)

| # | Treatment |
|---|-----------|
| 01 | full color (icon's own color/gradient) |
| 02 | white |
| 03 | black |

---

## 7. ENGINE PIPELINE

### 7.1 Ingest → working SVG

Convert the uploaded `.ai` (as PDF) to a single working SVG that preserves vector paths **and** gradient definitions (`linearGradient`/`radialGradient` with stops). This SVG is the single source for all generation and for the browser preview.

### 7.2 Preview coordinate mapping (frontend)

The browser renders the working SVG. The drag box is in screen pixels; convert to SVG user-space before sending to the backend:

```
scale  = svg.viewBox.width / renderedRect.width
svgX   = (screenX - renderedRect.left) * scale + svg.viewBox.minX
svgY   = (screenY - renderedRect.top)  * scale + svg.viewBox.minY
```

Send the box in SVG user-space coordinates. Never send pixel coordinates of a rasterized preview.

### 7.3 Icon selection (vector space, snap to whole paths)

Parse the working SVG into elements (with resolved transforms). For each top-level path/shape, compute its **bounding-box center (centroid)**. A path belongs to the **icon** group iff its centroid falls inside the selection box. **Snap to complete paths** — never split a path at the box edge. `wordmark = all paths − icon paths`. `full = all paths`.

If named layers/groups are present (`id`, `data-name`, `inkscape:label` ≈ `Icon`/`Logotype`/`Logo`), auto-assign and ask the CSR only to confirm.

### 7.4 Color & gradient detection + scope classification

Walk the icon and wordmark fills. Collect distinct solid colors and gradient defs. Surface as confirm-swatches. Classify the file:

- **solid** (1–3 solid colors) → supported.
- **linear/radial gradient present** → supported.
- **mesh/freeform gradient, embedded raster `<image>`, filter effects, in-artwork transparency, spot colors, live un-outlined text** → **out of scope → flag manual (§9). Do not attempt to ship.**

### 7.5 Treatment generation (produce variant SVGs)

Each treatment is a transform on the working SVG's path model:

- **full color:** fills unchanged.
- **all white:** every icon + wordmark fill (including gradient-filled paths) → `#fff`.
- **all black:** every fill → `#000` (or strip fills to default-black).
- **split:** icon group fills unchanged (solid or gradient); wordmark group → `#fff`.
- **with-background:** add a `<rect>` covering the full canvas (solid color, or rebuilt gradient — below). **transparent:** no rect; viewBox = tight artwork bbox.

**Gradient background (the precise rule — §6.4/02):** Do **not** paste the icon's gradient object onto the 1920×1080 rect. The icon's gradient is sized to a ~100 px mark; pasted onto a large rect with `userSpaceOnUse` it renders in a tiny corner and goes flat elsewhere. Instead, **build a new gradient**: copy the source **stop colors and offsets** and the **direction**, and set geometry to span the full canvas (`gradientUnits="objectBoundingBox"`, or recompute `userSpaceOnUse` coords to cover 0,0→1920,1080). Same colors, same angle, full bleed.

### 7.6 Placement & canvas (with-bg)

Build a `1920×1080` SVG. Center the logo, scale to fit within safe margins (§5.2), preserve aspect ratio.

### 7.7 Format export

- **SVG:** write the variant SVG.
- **PNG (transparent):** rasterize variant SVG → PNG at **1080 px width**, proportional height, alpha preserved.
- **JPG (with-bg):** rasterize the with-bg variant SVG at 1920×1080 → flatten → JPG.
- **PDF (with-bg & transparent):** SVG → vector PDF (gradients preserved).
- **`.ai` / `.eps`:** copy the uploaded files to root.

### 7.8 Package

Assemble the §5.1 tree with §5.3 naming, zip, return for download, delete the temp dir.

---

## 8. HARD RULES (MUST / MUST NOT)

These are non-negotiable. Each has an easy wrong implementation.

1. **MUST operate in vector space.** **MUST NOT** crop the preview image to produce the icon or any variant. Cropped pixels cannot become clean SVG/EPS/PDF.
2. **MUST read gradient definitions** (stops + geometry) directly from the vector and carry them through. **MUST NOT** eyedropper / pixel-sample to reconstruct a gradient — that is lossy *and* re-introduces the raster trap. The gradient is already a first-class vector object; read it, don't pick it.
3. **MUST select by whole-path centroid-in-box.** **MUST NOT** clip a path at the selection rectangle edge.
4. **For a gradient background, MUST rebuild a canvas-scale gradient** from the source stops/direction (§7.5). **MUST NOT** apply the mark-sized gradient object to the full-canvas rect.
5. **White knockout is the fixed treatment on any gradient background.** No luminance auto-pick on gradients — a gradient's brightness shifts across the canvas, so only white reads at both ends.
6. **Out-of-scope inputs (§7.4) MUST be flagged "manual" and refused.** **MUST NOT** rasterize-and-ship, silently approximate, or produce a half-broken file.
7. **RGB only.** No CMYK, no ICC profiles in v1.
8. **`.ai`/`.eps` are pass-through only.** Never regenerate or recolor them.
9. **Output tree, naming, and dimensions MUST match the fixture.** The fixture is the contract.

---

## 9. v1 SCOPE BOUNDARY

**In scope:** solid fills (1–3 colors) **and** linear/radial gradients; text outlined; side-by-side or stacked lockups (icon and wordmark spatially separable by a rectangle).

**Out of scope → flag "manual," refuse cleanly:** mesh/freeform gradients; embedded raster images; filter effects / drop shadows; in-artwork transparency; spot colors; live (un-outlined) text; **integrated lockups** where the mark is fused into a letter (e.g. icon replacing the "O") — a rectangle cannot separate those.

**Manual-flag behavior:** when an out-of-scope condition is detected, show the CSR a clear message naming the reason ("This logo contains a mesh gradient, which can't be auto-packaged — route to manual.") and do not generate a partial package.

---

## 10. REFERENCE FIXTURE (decoded) + ACCEPTANCE

`Fire_Systems_PNG_Limited_Files.zip` is the ground truth. Decoded facts:

- Clean vector SVGs (no embedded raster). Colors driven by reusable classes: red `#ec1c24`, navy `#112630`, white `#fff`. Black = SVG default (no fill).
- Two marks: **Logo** (full lockup) and **Icon** (bare flame).
- With-bg set: 5 treatments each for Icon and Logo. Transparent set: Icon ×3, Logo ×4.
- Root holds a single `.ai` and a single `.eps`.
- (Note: the fixture's with-bg artboards are square; **this build uses 1920×1080** per the locked spec. Treatment, recolor logic, recipe counts, naming, and the transparent set still match the fixture exactly.)

**Acceptance:** Feed a clean 2-color logo (or the fixture's primary mark). The produced package must (a) match the §5.1 tree and §5.3 naming, (b) apply §6 treatments correctly, (c) preserve vector throughout (open an output SVG — it must contain paths, not an embedded image), (d) keep linear/radial gradients intact in the gradient case, (e) deliver transparent PNGs at 1080 px width proportional and with-bg files at 1920×1080.

---

## 11. BUILD MILESTONES (each has a gate — don't skip)

- **M0 — Scaffold.** Repo, React+Vite+Tailwind front, FastAPI back, toolchain binaries installed, health check. *Gate:* app runs locally.
- **M1 — Ingest → working SVG.** `.ai` → SVG; evaluate `pdf2svg` vs Inkscape on gradient fidelity. *Gate:* a known linear/radial-gradient logo converts with the gradient intact as an SVG gradient def (not flattened, not rasterized).
- **M2 — Selection.** Path model, centroid-in-box icon selection, wordmark-as-remainder, named-layer auto-detect; minimal preview UI with the §7.2 coordinate mapping. *Gate:* selecting the flame on the fixture's primary mark yields icon-only paths, vector preserved; wordmark = remainder.
- **M3 — Color/gradient detect + scope classifier.** Confirm-swatches; solid / linear-radial / out-of-scope routing. *Gate:* fixture colors detected; a mesh/raster test file is correctly flagged manual.
- **M4 — Treatment engine.** The §6 recipes as SVG transforms, including white-knockout-on-rebuilt-gradient-background (§7.5). *Gate:* all treatments render correctly for both a solid and a gradient test logo.
- **M5 — Exporters.** SVG, PNG@1080 transparent, JPG 1920×1080, PDF (both); `.ai`/`.eps` pass-through. *Gate:* every format opens correctly; output SVGs contain paths; PDFs are vector.
- **M6 — Packager.** Exact §5.1 tree + §5.3 naming → zip → download. *Gate:* output tree structurally matches the fixture; spot-checked renders match treatments.
- **M7 — Manual-flag UX + error handling.** Clear refusal messaging for out-of-scope files; temp-dir cleanup verified. *Gate:* out-of-scope file produces a clean flag, no partial zip; no temp files left behind.

---

## 12. DEFERRED TO v2 (do not build now)

- **CMYK** output (CMYK PDF/EPS/JPG) + ICC profile selection (US Web Coated SWOP v2 default, FOGRA39 for EU/DK/DE). CMYK SVG will **never** be built — SVG is RGB by specification.
- Mesh/freeform gradient support.
- Everything else listed out-of-scope in §9.
- Any integration with HaseebMadeIt OS (order-ID pull/push) — only if/when the pipeline needs it as an automated step.
