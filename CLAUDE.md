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
- **Artboard = fixed 1920×1080** on every with-background format. SVG/PDF carry
  `viewBox 0 0 1920 1080`; **JPEG exports @2× = 3840×2160**. (Not square, not
  per-source-artboard — fixed 1920×1080.)
- **Folder named `JPEG`** (client-facing term; file extension stays `.jpg`).
- **Naming:** `Icon 01 … Icon 05`, `Logo 01 … Logo 05` — **zero-padded two
  digits, space before the number.** Root folder `[Brand Name] Files`.
- **Tree:**
  ```
  [Brand] Files/
  ├─ [Brand].ai · [Brand].eps        ← pass-through, untouched, single masters at root
  ├─ JPEG/  Icon 01–05 · Logo 01–05  (3840×2160, with background)
  ├─ PDF/   Icon 01–05 · Logo 01–05  (vector, 1920×1080)
  ├─ SVG/   Icon 01–05 · Logo 01–05  (vector, 1920×1080)
  └─ Transparent/                    (edge-to-edge, no background)
     ├─ PNG/  Icon 01–03 · Logo 01–04   (raster, 2160px wide @2×, alpha)
     ├─ SVG/  Icon 01–03 · Logo 01–04   (vector, tight bbox)
     └─ PDF/  Icon 01–03 · Logo 01–04   (vector, tight bbox)
  ```
  51 generated files + the 2 pass-through originals.
- **Icon set is OPTIONAL.** No icon box marked (and no named layers) → generate
  the **logo set only** (27 files). Never force/auto-ship an icon the CSR didn't ask for.
- **Ignore extras** found in reference zips — social cover photos
  (Facebook/LinkedIn/Twitter-X/YouTube), brand guidelines, business cards,
  Instagram templates, per-variant EPS, AI/EPS-in-folders. Not generated.
  (Possible future feature: auto social covers — flagged, not built.)
- **Raster quality:** @2× (env `LOGO_EXPORT_SCALE`, default 2), JPEG quality 95
  (4:4:4). SVG/PDF stay vector. Transparent PNG = 1080px logical @2× = 2160px wide.

## Treatments (§6 recipes — `backend/app/recipes.py`)
Background pool per slot: `[white, brand-A, brand-B, white, black]`. brand-A =
darker brand color, brand-B = more vivid; for a 1-color logo brand-B → black.
- **Solid Logo 01–05:** white/full · brand-A/split (icon keeps color, wordmark→white) ·
  brand-B/all-white · white/all-black · black/all-white.
- **Solid Icon 01–05:** white/full · brand-A/full · brand-B/white · white/black · black/white.
- **Gradient Logo/Icon:** 01 white/full · 02 **white knockout on a rebuilt
  full-bleed gradient** (hero) · 03 black/white · 04 white/black · 05 dark-stop-solid/white.
- **Transparent Logo 01–04:** full · split · white · black. **Icon 01–03:** full · white · black.

### Hard rules (where the easy implementation is wrong)
- Operate in **vector space**; never crop a preview or pixel-sample a gradient.
- Gradient backgrounds: **rebuild** a canvas-scale gradient from source stops +
  direction (`objectBoundingBox`, full-bleed). White knockout is fixed on any
  gradient background.
- **Contrast guard** (`treatments._ensure_contrast`): on any solid background,
  if an element's fg/bg contrast < ~2.2 it's knocked out to white/black —
  whichever reads. Fixes single-color logos on their own brand color (purple-on-
  purple). Well-contrasting 2-color logos (red on navy) are left alone.
- **Out of scope → flag "manual," refuse** (no partial zip): mesh/freeform
  gradients, embedded raster `<image>`, filters/shadows, in-art transparency,
  spot colors, live (un-outlined) text, integrated lockups.
- `.ai`/`.eps` are **pass-through only** — never recolor/regenerate them. RGB only.

## Engine behaviors learned from real files (keep these)
- **Source page background rect** (pdf2svg/Illustrator add one) is detected and
  **excluded** from artwork (bbox/selection/colors/output) so the logo isn't
  tiny/off-center and colors aren't polluted. Never flag everything as bg.
- **Placement:** logo fit within 65% of each canvas dim, centered on the
  **visible (rendered) bbox** (robust to invisible/fill:none guides). Icon
  re-centered, longest side ≈ 30% of the shorter canvas dim.
- **Icon auto-extraction** (`selection.auto_icon`) when a box misses: split the
  lockup at its largest gap on the best axis (handles stacked lockups like an
  emblem over a wide wordmark) and take the more square cluster as the icon.
- **pdf2svg quirks:** colors come as `rgb(%, %, %)` (normalize before luminance,
  else crashes); coords scale pt→px (~0.75). Each artboard = a PDF page.
- **Multi-artboard:** convert every page; the CSR **must pick the primary logo**
  when >1. De-dup treatment-variants of one mark by geometry; suggest the most
  complete full-color lockup.
- **Brand colors:** rank by area; brand-A = darkest chromatic, brand-B = most
  vivid. Exclude neutrals by **saturation** (so dark-but-chromatic navy stays a
  brand color; near-black/gray artifacts don't).

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
