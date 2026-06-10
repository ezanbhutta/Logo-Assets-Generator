# CLAUDE.md — Logo Package Engine

Project conventions and standards for this repo. Read this first; it is the
source of truth for how the engine must behave. `BUILD_SPEC.md` is the original
brief — where this file disagrees with it, **this file wins** (it reflects later
decisions by the owner).

## What this is
A stateless web tool: a CSR uploads a logo's `.ai` (+ `.eps`), optionally marks
the icon on a vector preview, confirms detected colors, and downloads a complete
logo delivery package as a `.zip`. Upload → zip out. No DB, no auth.

- **Backend:** Python + FastAPI (`backend/app/`). Endpoints: `POST /ingest`,
  `POST /generate`, `GET /health`. Stateless per-job temp dirs, cleaned on
  completion.
- **Frontend:** React + Vite + Tailwind (`frontend/`). Live **true-vector** SVG
  preview; icon box mapped to SVG user space.
- **Vector toolchain:** `pdf2svg` (.ai→SVG, gradients preserved), `svgelements`
  (geometry), `lxml` (fill model/edits), `cairosvg` (PNG/JPEG), `rsvg-convert`
  (vector PDF). Needs native binaries → **deploy on Docker/Render, not Vercel.**

## LOCKED OUTPUT STANDARD (do not drift)
- **Artboards (owner standard):** every with-background **LOGO** format = fixed
  **1920×1080** (`viewBox 0 0 1920 1080`; JPEG @2× = 3840×2160). Every
  with-background **ICON** format = fixed **1080×1080 SQUARE**
  (`viewBox 0 0 1080 1080`; JPEG @2× = 2160×2160). The mark is **proportionally**
  scaled — never stretched or skewed — so its binding side spans **60%**
  (`SAFE_FRACTION`) of the artboard, centered (balanced) on its visible bbox.
  JPEG dimensions derive from each variant's own artboard (`exporters.write_jpg`
  reads the viewBox — forcing one size would skew the square icons).
- **Folder named `JPEG`** (client-facing term; file extension stays `.jpg`).
- **Naming:** `Icon 01 … Icon 05`, `Logo 01 … Logo 05` — **zero-padded two
  digits, space before the number.** Root folder `[Brand Name] Files`.
- **Tree:**
  ```
  [Brand] Files/
  ├─ [Brand].ai · [Brand].eps        ← masters at root, ONLY the selected artboard
  ├─ JPEG/  Icon 01–05 (2160×2160) · Logo 01–05 (3840×2160)  (with background)
  ├─ PDF/   Icon 01–05 (1080²) · Logo 01–05 (1920×1080)      (vector)
  ├─ SVG/   Icon 01–05 (1080²) · Logo 01–05 (1920×1080)      (vector)
  └─ Transparent/                    (edge-to-edge, no background — unchanged)
     ├─ PNG/  Icon 01–03 · Logo 01–04   (raster, 2160px wide @2×, alpha)
     ├─ SVG/  Icon 01–03 · Logo 01–04   (vector, tight bbox)
     └─ PDF/  Icon 01–03 · Logo 01–04   (vector, tight bbox)
  ```
  51 generated files + the 2 pass-through originals.
- **Icon set is OPTIONAL.** No icon box marked (and no named layers) → generate
  the **logo set only** (27 files). Never force/auto-ship an icon the CSR didn't ask for.
- **Ignore extras** found in reference zips — social cover photos
  (Facebook/LinkedIn/Twitter-X/YouTube), brand guidelines, business cards,
  Instagram templates, **iconography sets**, per-variant EPS, AI/EPS-in-folders,
  bare `Artboard N` exports. Not generated. (Possible future feature: auto
  social covers — flagged, not built.)
- **Treatment counts are fixed at 5+5 (with-bg) / 3+4 (transparent).** Some
  older packages ran extended sets (e.g. Logo 01–10); the locked standard is 5.
- **Raster quality:** @2× (env `LOGO_EXPORT_SCALE`, default 2), JPEG quality 95
  (4:4:4). SVG/PDF stay vector. Transparent PNG = 1080px logical @2× = 2160px wide.

## Treatments (§6 recipes — `backend/app/recipes.py`)
Background pool per slot: `[white, brand-A, brand-B, white, black]`. brand-A =
darker brand color, brand-B = more vivid; for a 1-color logo brand-B = a **deep
shade of the brand color** (`colors.shade_of`, in-scheme — not plain black). A
**neutral-only** logo (black wordmark, no chromatic color) gets its own neutral
scale instead: brand-A = a charcoal tint, brand-B = a light gray on which the
mark keeps its true ink — never three identical black slots.
- **Solid Logo & Icon 01–05:** white/full · brand-A/**adaptive** ·
  brand-B/**adaptive** · white/all-black (mono) · black/all-white (mono).
- **Gradient Logo/Icon:** 01 white/full · 02 **white knockout on a rebuilt
  full-bleed gradient** (hero) · 03 black/**adaptive** (the gradient is KEPT on
  black when its tone reads — a vivid gradient glows there; swapped to a readable
  solid when it would vanish) · 04 white/black · 05 dark-stop-solid/white.
- **Transparent Logo 01–04:** full · split · white · black. **Icon 01–03:** full · white · black.

### Adaptive recolor (the designer engine — `treatments._ensure_contrast`)
"Adaptive" = recolor `full` + the layer-aware contrast guard. On any colored
background the artwork **keeps every color that reads** (≥ ~2.2:1 against its
actual backdrop) — never blanket-white on colored backgrounds. Each color that
would vanish is swapped, in order of preference, to:
1. the **most similar color from the logo's OWN palette** that genuinely reads
   (≥ 4.5:1) — a brown mascot outline on the brown brand bg becomes the mascot's
   cream, never an out-of-scheme color;
2. else **white/black** — white preferred when it clears ~3:1 (the classic mark
   on saturated brand colors); black only on genuinely light backgrounds.
Layer-aware throughout: an element is judged against what is actually behind it
(a larger shape beneath, by paint order — including a gradient shape's average
tone — else the canvas), so white detail on a purple gear survives a white
canvas, and substituted colors cascade (elements above see the new color below).
Gradient-filled elements are judged by their **average stop tone** on non-white
backdrops; on white (the canonical full-color slot) they are always kept. Mono
(white/black) treatments never substitute palette colors — nested detail flips
white↔black so the pattern stays visible; mono stays mono. This one mechanism
handles wordmarks, combination marks, multi-color mascots, and gradient marks.

### Hard rules (where the easy implementation is wrong)
- Operate in **vector space**; never crop a preview or pixel-sample a gradient.
- Gradient backgrounds: **rebuild** a canvas-scale gradient from source stops +
  direction (`objectBoundingBox`, full-bleed). White knockout is fixed on any
  gradient background.
- Substitutions must stay **in the logo's color scheme** (its own palette, plus
  the white/black knockouts) — the engine never invents an outside color.
- **Out of scope → flag "manual," refuse** (no partial zip): mesh/freeform
  gradients, embedded raster `<image>`, filters/shadows, in-art transparency,
  spot colors, live (un-outlined) text, integrated lockups.
- `.ai`/`.eps` masters carry **only the selected artboard** (owner override of the
  old "untouched pass-through"). Never recolor; RGB only. A PDF-compatible `.ai`
  stores each artboard as a PDF page **and** a whole-document native (PGF) copy in
  each page's `/PieceInfo`; `masters.py` extracts the chosen page and **strips that
  native blob** so Adobe honors the single artboard (it rebuilds from the page's
  editable vectors), and re-renders the `.eps` from the same page via `pdftops`.
  Single-artboard or non-PDF sources are still copied **untouched** (a native single
  `.ai` stays native — nothing to carve).

## Engine behaviors learned from real files (keep these)
- **Source page background rect** (pdf2svg/Illustrator add one) is detected and
  **excluded** from artwork (bbox/selection/colors/output) so the logo isn't
  tiny/off-center and colors aren't polluted. Never flag everything as bg.
- **Placement:** the mark's binding side spans 60% of its artboard (logo
  1920×1080, icon 1080×1080), proportional, centered on the **visible
  (rendered) bbox** (robust to invisible/fill:none guides).
- **Icon auto-extraction** (`selection.auto_icon`) when a box misses: split the
  lockup at its largest gap on the best axis (handles stacked lockups like an
  emblem over a wide wordmark) and take the more square cluster as the icon.
- **Auto-segmentation** (`selection.auto_segment`, on ingest): read the artboard
  like a designer and **pre-fill editable logo + icon boxes**. Cluster ink by
  spatial proximity (gap ∝ median element size, so it transfers from a tight
  cropped lockup to a sprawling brand sheet); detect color **swatches** (≥3
  aligned, similar-size, square-ish chips) and exclude them; **assemble the
  lockup** = richest cluster + nearby *aligned* pieces (rescues a symbol that
  split off the wordmark), while far-off duplicates/strays stay out; mark the
  icon = the set-apart square sub-region (only when convincing — never carves a
  letter out of plain text). Handles the **bento/brand-sheet** case (logo +
  standalone icon + swatches + variations on one artboard) and the *icon-derived-
  from-wordmark* case. It is a **suggestion only** — the CSR reviews/adjusts the
  two boxes; nothing ships on auto-detection alone. Returns `None` (normal flow)
  for a plain single wordmark.
- **pdf2svg quirks:** colors come as `rgb(%, %, %)` (normalize before luminance,
  else crashes); coords scale pt→px (~0.75). Each artboard = a PDF page. **Text is
  emitted as hundreds of `<use>` of glyph outlines in `<defs>`** — invisible to
  selection/geometry yet still painted, so a brand sheet's headings/body copy
  leak into every export. `svgutil.flatten_uses` (run in `WorkingSVG.__init__`)
  inlines every `<use>` into a positioned copy, turning that text into normal
  tagged paths that can be measured, selected, and pruned like the rest.
- **Presentation panels** (`selection._panel_ids`): a brand sheet lays each logo
  variation on a repeated tile. A panel = a large element (≥8% of the artboard)
  that backs ≥2 marks **and** has a similar-size peer (the repetition is the
  giveaway — a lone logo shape like a gear never has a twin, so it's never mis-
  flagged). Panels are dropped from the logo so a box over a tile yields the
  lockup, not the tile rectangle. The **icon box is independent of the logo box**
  — it may mark a sub-region of the lockup or a standalone mark on its own tile
  (an icon derived from the wordmark), and the icon files come from exactly what
  it covers. An **explicitly-drawn box is authoritative**: it selects the
  covered marks (with a forgiving overlap retry so a slightly-loose rectangle
  around a small standalone mark still grabs it). A drawn box that covers **no
  artwork** makes `/generate` refuse with a 422 `box_miss` (job kept alive for
  the retry) — never silently ship a logo-only zip, never ship the whole sheet
  as the logo, and **never** auto-carve an icon substitute out of the wordmark
  (the Tays standalone-`t.` bug). A logo box that slices a word mid-row is
  snapped to designer intent: `selection._complete_row` extends it along the
  baseline to the whole glyph run (the live `'ta'` bug — half a wordmark is
  never what the CSR meant), then `_attach_punct` keeps the trailing period.
  Auto/named icon detection applies only when **no** icon box was drawn (the
  optional-icon convenience path).
- **Multi-artboard:** convert every page; the CSR **must pick the primary logo**
  when >1. De-dup treatment-variants of one mark by geometry; suggest the most
  complete full-color lockup.
- **Brand colors:** rank by area; brand-A = darkest chromatic, brand-B = most
  vivid. Exclude neutrals by **saturation** (so dark-but-chromatic navy stays a
  brand color; near-black/gray artifacts don't).

## AI segmentation (vision-in-the-loop — `backend/app/vision.py`)
The geometric `selection.auto_segment` heuristics approximate a designer's eye
but are brittle (every odd file finds a gap between the rules). The **Auto-detect**
button now calls `POST /segment`, which renders the chosen artboard and asks
**Claude (vision, `claude-fable-5`)** to read it like a designer and return the
editable **logo_box / icon_box** (normalized fractions → mapped to SVG user
space). It is a **suggestion only** — the CSR still reviews/adjusts; nothing
ships on detection alone.
- **Opt-in + graceful:** active only when `ANTHROPIC_API_KEY` is set. Any failure
  (no key, SDK missing, network, bad JSON) returns `None` and `/segment` falls
  back to `selection.auto_segment` (`source: "ai" | "geometry" | "none"`). Fully
  backward-compatible — nothing changes until the key is configured.
- **Env:** `ANTHROPIC_API_KEY` (enables it), `LOGO_AI_MODEL` (default
  `claude-fable-5`), `LOGO_AI_MAX_PX` (rendered preview width, default 1400).
- The model does **perception/grouping** (what's the lockup, the icon, the
  scaffolding); the engine still does the **geometry** — the returned boxes feed
  the same `selection.select` two-box flow (panel-strip, `_attach_punct`, etc.).
- **Privacy:** with a key set, the rendered artboard is sent to the Anthropic API
  (not used for training). The geometric path keeps everything local.

## Design system (CSR-Pulse / HaseebMadeIt)
Match `csr-pulse-vbsz.vercel.app`.
- **Primary purple `#7229ff`** (`pulse-500`), **ink `#160a33`**, page bg
  `#f4f2fa` with soft purple radial gradients, **white rounded-2xl cards**.
- **Inter** font. Buttons/badges/active states on the pulse accent.
- **Logo:** the exact brand mark is `frontend/public/favicon.svg` (purple tile +
  white grid/pulse mark). It is the favicon AND the in-app top-bar icon
  (`PulseMark` renders `/favicon.svg`). Do not redraw it — use that file.

## Dev / test / deploy
```bash
./scripts/setup.sh                                   # toolchain + venv + npm
.venv/bin/python -m pytest                           # backend tests (must stay green)
.venv/bin/uvicorn app.main:app --app-dir backend --reload   # API + serves frontend/dist
cd frontend && npm run dev                           # UI (proxies API)
```
- **Deploy:** `Dockerfile` (multi-stage) on **Render** (`render.yaml` blueprint).
  Honors `$PORT`. Serves UI + API from one origin. Not Vercel (needs native bins).
- **Branch:** develop on `claude/affectionate-euler-sFiaC`. Commit with clear
  messages; don't merge/deploy without the owner's go-ahead.

## When given new reference packages
Read them as the source of truth for conventions, but the **LOCKED OUTPUT
STANDARD above wins** over any one package's quirks (older packages vary:
`Icon 1` vs `Icon 01`, mixed sizes, extras). Extract genuine rules; ignore
typos and one-off human choices.
