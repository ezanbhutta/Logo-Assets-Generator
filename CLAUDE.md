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
  preview; screen↔user-space mapping goes through the **injected artwork SVG's
  own `getScreenCTM()`** (the browser's ground-truth transform for what it
  rendered), and overlay boxes are positioned via that same CTM. Never
  hand-rolled rect math and never a separate viewBox guess — a converter whose
  px scale differed from the `viewbox` prop silently mis-mapped boxes, so a box
  drawn on the mark missed it server-side.
- **Coordinate space is normalized at ingest** (`WorkingSVG._ensure_viewbox`):
  some poppler builds emit width/height but no viewBox (and the px scale varies
  host-to-host). A viewBox is derived from width/height so the served SVG,
  `viewbox`, svgelements geometry, and the browser all share ONE space —
  otherwise `viewbox` fell back to the ink bbox (different origin/aspect) and the
  preview overlay drifted from the artwork.
- **Vector toolchain:** `pdf2svg` (.ai→SVG, gradients preserved), `svgelements`
  (geometry), `lxml` (fill model/edits), `cairosvg` (PNG/JPEG), `rsvg-convert`
  (vector PDF). Needs native binaries → **deploy on Docker/Render, not Vercel.**

## LOCKED OUTPUT STANDARD (do not drift)
- **Artboards (owner standard):** every with-background **LOGO** format = fixed
  **1920×1080** (`viewBox 0 0 1920 1080`; JPEG @2× = 3840×2160). Every
  with-background **ICON** format = fixed **1080×1080 SQUARE**
  (`viewBox 0 0 1080 1080`; JPEG @2× = 2160×2160). The mark is **proportionally**
  scaled — never stretched or skewed — centered (balanced) on its visible bbox.
  Binding side: **LOGO 60%** (`SAFE_FRACTION`; references 50–65%), **ICON 42%**
  (`ICON_SAFE_FRACTION`; references 29–44%, Pulse 44% — icons sit smaller than
  logos, validated in `REFERENCE_STUDY.md`). JPEG dimensions derive from each
  variant's own artboard (`exporters.write_jpg` reads the viewBox — forcing one
  size would skew the square icons).
- **Folder named `JPEG`** (client-facing term; file extension stays `.jpg`).
- **Naming:** `Icon 01 … Icon 05`, `Logo 01 … Logo 05` — **zero-padded two
  digits, space before the number.** Root folder `[Brand Name] Files`.
- **Tree:**
  ```
  [Brand] Files/
  ├─ [Brand].ai · [Brand].eps        ← masters at root, ONLY the selected artboard
  ├─ JPEG/  Icon 01–06 (2160×2160) · Logo 01–06 (3840×2160)  (with background)
  ├─ PDF/   Icon 01–06 (1080²) · Logo 01–06 (1920×1080)      (vector)
  ├─ SVG/   Icon 01–06 (1080²) · Logo 01–06 (1920×1080)      (vector)
  └─ Transparent/                    (edge-to-edge, no background — unchanged)
     ├─ PNG/  Icon 01–03 · Logo 01–04   (raster, 2160px wide @2×, alpha)
     ├─ SVG/  Icon 01–03 · Logo 01–04   (vector, tight bbox)
     └─ PDF/  Icon 01–03 · Logo 01–04   (vector, tight bbox)
  ```
  57 generated files + the 2 pass-through originals.
- **Icon set is OPTIONAL.** No icon box marked (and no named layers) → generate
  the **logo set only** (27 files). Never force/auto-ship an icon the CSR didn't ask for.
- **Ignore extras** found in reference zips — social cover photos
  (Facebook/LinkedIn/Twitter-X/YouTube), brand guidelines, business cards,
  Instagram templates, **iconography sets**, per-variant EPS, AI/EPS-in-folders,
  bare `Artboard N` exports. Not generated. (Possible future feature: auto
  social covers — flagged, not built.)
- **Treatment counts: 6+6 (with-bg solid) / 3+4 (transparent).** The solid
  with-background set ships **both** monochromes as their own slides — 05 black
  on white, 06 white on black (owner decision, PACK session). The **gradient**
  with-bg set stays 5 (it already carries both monos within its standard).
- **Raster quality:** @2× (env `LOGO_EXPORT_SCALE`, default 2), JPEG quality 95
  (4:4:4). SVG/PDF stay vector. Transparent PNG = 1080px logical @2× = 2160px wide.

## Treatments (§6 recipes — `backend/app/recipes.py`)
**The SOLID with-background set is the owner's trained recipe** (PACK FRESH CLUB
session), built **per-logo from its real palette** by `recipes.build_solid` — not
a static table, because slots 02–04 depend on the brand colors. The five slots:

- **01 — white / primary, exactly as authored.** The designer's own colors, with
  **no recolor and no contrast "fixing"** (the guard never runs on the white
  primary). A soft periwinkle stays periwinkle; a same-gray pyramid base stays
  gray. (Both the PACK and Aurora bugs were the guard mangling this slot —
  whitening/blackening the primary. It is now untouchable.)
- **02 — dark / the SAME logo on the dark field.** Background = the **darkest
  shade used in the logo** (a navy, a deep brown — `recipes._dark_background`,
  luminance < 0.20), or **BLACK** when the logo has no dark shade. The logo lands
  **verbatim** (recolor `keep`): a color is lifted only when it would vanish on
  the **field itself** — canvas-only, never judged against a sibling stroke, so a
  layered/offset wordmark (PACK's blue+yellow ribbons) lands intact on black.
- **03 · 04 — the two brand colors as fields: the color-SWAP pair.** When the
  logo has exactly **two** brand colors that look good on each other
  (`colors.colors_harmonize`), each brand field carries the **OTHER** brand color,
  **flat**: e.g. **full yellow logo on the blue field, full blue logo on the
  yellow field**. When the two colors would **clash** (both bold & saturated with
  little tonal separation — they vibrate; or near-identical so the mark vanishes)
  it falls back to the designer mono: a **white** mark on the darker field, a
  **black** mark on the lighter field. (1-color / neutral / 3+-color marks have no
  clean swap, so their brand fields keep the **adaptive** full recolor instead —
  see below. An exception to refine over time.)
- **05 — white / one-color BLACK monochrome · 06 — black / one-color WHITE
  monochrome (reversed).** The owner ships **both** monochromes as their own
  slides. (The transparent set also carries both one-color marks.)

- **Gradient Logo/Icon (unchanged designer standard):** 01 white/full · 02 **white
  knockout on a rebuilt full-bleed gradient** (hero) · 03 **black/white knockout**
  (Orova; a gradient's tone shifts across the mark, so only white reads cleanly on
  black) · 04 white/black · 05 dark-stop-solid/white. Gradient stop colors are
  folded into brand ranking (`colors.detect`) so brand-A/brand-B reflect the real
  hues, not a gray outline.
- **Transparent Logo 01–04:** full · split · white · black. **Icon 01–03:** full · white · black.

### Recolor modes (`treatments._recolor` / `_ensure_contrast`)
- **`full`** — keep authored fills; the **layer-aware** contrast guard substitutes
  only what would vanish. On a colored field the artwork **keeps every color that
  reads** (≥ ~2.2:1 against its actual backdrop), and each one that doesn't is
  swapped, in order, to (1) the **most similar color from the logo's OWN palette**
  that genuinely reads (≥ 4.5:1) — a brown mascot outline on the brown brand field
  becomes the mascot's cream — else (2) **white/black** (white preferred ≥ ~3:1).
  Layer-aware: an element is judged against the larger shape **fully containing**
  it (≥ 2.5× its area — a true backdrop, not a sibling stroke), so white detail on
  a purple gear survives, and substitutions cascade. **On a WHITE field the guard
  does not run at all** — the full-color primary is always the logo as authored.
- **`keep`** (slot 02) — same as `full` but **canvas-only**: judged against the
  field, never a sibling stroke. "Put the same on the dark background."
- **`flat`** (slots 03/04 swap) — recolor **every** fill/stroke to one color (the
  other brand color, or a knockout). A deliberate single color — **no guard**.
- **`white` / `black`** (mono) — every fill → white/black; never a palette color.
- Substitutions stay **in the logo's scheme** (its palette + white/black) — never
  an invented outside color. Handles wordmarks, combination marks, mascots, and
  (via the gradient set) gradient marks.

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
- **Placement:** binding side = **60% logo / 42% icon** of its artboard (logo
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
  letter out of plain text). The icon may be set apart **horizontally** (a leaf
  before a wordmark) OR **stacked above/below** it (`_lockup_icon` splits on the
  best axis — a gear/shield over the name is detected, the Orova combination-mark
  case that previously shipped no icon). Handles the **bento/brand-sheet** case
  (logo + standalone icon + swatches + variations on one artboard), the *icon-
  derived-from-wordmark* case, and the plain **combination mark** (symbol +
  wordmark). It is a **suggestion only** — the CSR reviews/adjusts the
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
