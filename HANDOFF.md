# Logo Package Engine — Project Handoff & Learnings

> **Purpose of this file.** A self-contained brief so a fresh chat can understand
> this project and everything decided/learned so far, then continue without
> repeating mistakes. The **living source of truth is `CLAUDE.md`** (detailed
> conventions, kept current); `BUILD_SPEC.md` is the original brief;
> `REFERENCE_STUDY.md` is the research on real designer packages. Where this file
> and `CLAUDE.md` agree, `CLAUDE.md` wins for fine detail. Read `CLAUDE.md` next.

Owner: HaseebMadeIt. Repo: `ezanbhutta/Logo-Assets-Generator` (public).
Dev branch: `claude/affectionate-euler-sFiaC`. Deploy: **Render**, auto-deploy on
push to `main` (we merge the dev branch → `main` to ship). 119 backend tests green.

> **⚠ Parallel development — read this.** This repo is being built by more than
> one chat at once, all pushing to `main`. Good news: the work has **layered
> cleanly, not conflicted** — the other line branched directly off this chat's
> foundation. As of this writing `main` has already advanced **beyond** what
> this doc's status section lists, with further recipe work: detecting and
> **leading with the logo's authored background color** (including light-but-
> saturated fields, e.g. a cream `#fffccf`), deriving a **two-tone** icon/text
> split, never shipping two identical slides, tagging **named lockups**
> (Secondary / Horizontal / Vertical…) and a typography-only **Text** set, and
> **removing the deep-shade fallback** (no invented colors, ever). For the exact
> current behavior, **`CLAUDE.md` on `main` is authoritative** — this file is the
> foundation, the owner's training, and the reasoning/bugs behind it. To avoid
> collisions, coordinate which chat owns `main` at a given time, or work on
> separate branches and merge.

---

## 1. What this is
A **stateless web tool**: a CSR uploads a logo's `.ai` (+ optional `.eps`),
tags which artboard is the Logo and which is the Icon, confirms the detected
brand colors, and downloads a complete **logo delivery package** as a `.zip`.
Upload → zip out. No database, no auth, no persistence (each job is a temp dir,
deleted after the zip streams).

- **Backend:** Python + FastAPI (`backend/app/`). Endpoints: `POST /ingest`,
  `POST /generate`, `POST /segment`, `GET /health`.
- **Frontend:** React + Vite + Tailwind (`frontend/`). Live **true-vector** SVG
  preview; the CSR draws boxes on the artwork.
- **Vector toolchain (native binaries → must deploy on Docker/Render, not
  Vercel):** `pdf2svg` (.ai→SVG, keeps gradients), `svgelements` (geometry),
  `lxml` (fill edits), `cairosvg` (PNG/JPEG), `rsvg-convert` (vector PDF),
  `pypdf`/`pdftops` (masters).

---

## 2. THE TRAINED TREATMENT RECIPE (most important — the owner taught this directly)

This is the heart of the tool and where past versions kept going wrong. The
**solid, with-background set is built per-logo from its real palette** by
`recipes.build_solid(report, mark)` — NOT a static table, because slots 03/04
depend on the two brand colors. **Six slides** (owner decision — both
monochromes ship as their own slides):

| # | Field (background) | Mark | Rule |
|---|---|---|---|
| **01** | white | full color, **exactly as authored** | The primary. The contrast guard **never runs on white** — never "fix"/recolor it. A soft periwinkle stays periwinkle. |
| **02** | the **darkest shade in the logo**, else **black** | the **same** logo | "Put the same on the dark field." A color is lifted to white **only if it would vanish on the field itself** (canvas-only). |
| **03** | brand color A | **flat** full brand color B | The color-**swap** pair: e.g. full **yellow** logo on the **blue** field. |
| **04** | brand color B | **flat** full brand color A | e.g. full **blue** logo on the **yellow** field. |
| **05** | white | **black** monochrome | one-color black. |
| **06** | black | **white** monochrome | one-color white (reversed). |

**Swap vs. clash (slots 03/04).** Default is the two-color swap (each brand
field carries the *other* brand color, flat). But if the two colors **wouldn't
look good on each other** — they clash — fall back to the designer mono:
**white mark on the darker field, black mark on the lighter field**
(e.g. white-on-blue / black-on-yellow). The judgment is
`colors.colors_harmonize(a, b)`:
- **False** (→ mono fallback) when the two colors are nearly identical (mark
  would vanish) OR both bold & saturated with little tonal separation (they
  vibrate — e.g. saturated red on saturated green).
- **True** (→ swap) otherwise — the common case. Two pastels swap; navy/gold
  swap; soft-blue/soft-yellow swap.

**Only when the logo has exactly two chromatic brand colors** do slots 03/04
swap. A **1-color, neutral, or 3+-color** mark has no clean two-color swap, so
those slots keep the **adaptive full recolor** on the brand fields instead (see
recolor `full` below) — flagged as an exception to refine over time.

**Recolor modes** (`treatments._recolor` / `_ensure_contrast`):
- **`full`** — keep authored fills; a **layer-aware** contrast guard substitutes
  only a color that would vanish, to (1) the nearest in-palette color that reads
  (≥ 4.5:1), else (2) white/black (white preferred ≥ ~3:1). Layer-aware = judged
  against the shape that **fully contains** it and is **≥ 2.5× its area** (a real
  backdrop like a gear behind its cut-out — NOT a sibling stroke). **On a white
  field the guard does not run at all.**
- **`keep`** (slot 02) — like `full` but **canvas-only** (judged against the
  field, never a sibling stroke), so a layered/offset wordmark lands verbatim.
- **`flat`** (slots 03/04 swap/clash) — recolor **every** fill/stroke to one
  color; a deliberate single color, **no guard**.
- **`white` / `black`** (mono) — every fill → white/black; never a palette color.
- Substitutions **stay in the logo's own scheme** (its palette + white/black).
  The engine never invents an outside color.

**Gradient logos** keep the separate 5-slide designer standard (white/full ·
white-knockout on rebuilt full-bleed gradient · white-on-black · black-on-white ·
white-on-dark-stop) — it already carries both monos, so it stays 5.

**Transparent set** (edge-to-edge, no background): Logo 01–04 = full · split ·
white · black. Icon 01–03 = full · white · black. (This is where both one-color
marks always ship regardless of logo type.)

### The bug this replaced (do NOT regress)
The old "adaptive" engine ran its contrast guard on the **white primary** and
recolored it — on PACK FRESH CLUB it turned 42 of 53 elements **black**,
destroying the periwinkle. The owner's repeated, emphatic instruction: **the
white primary is the logo exactly as the designer authored it. Never touch it.**

---

## 3. Package output standard (LOCKED)
- **Artboards:** every with-bg **LOGO** = **1920×1080** (`viewBox 0 0 1920 1080`;
  JPEG @2× = 3840×2160). Every with-bg **ICON** = **1080×1080 square**
  (JPEG @2× = 2160×2160). Mark is **proportionally** scaled (never stretched),
  centered on its **visible (rendered) bbox**. Binding side: **LOGO 60%**
  (`SAFE_FRACTION`), **ICON 42%** (`ICON_SAFE_FRACTION`).
- **Counts:** with-bg solid **6+6**, transparent **4+3**. Total **57 generated
  files + 2 pass-through masters (.ai/.eps)** when an icon is included; logo-only
  = 30 generated.
- **Naming:** `Icon 01 … Icon 06`, `Logo 01 … Logo 06` — zero-padded two digits,
  space before the number. Root folder `[Brand] Files`. `JPEG` folder is the
  client-facing name (extension stays `.jpg`).
- **Tree:** masters at root · `JPEG/` `PDF/` `SVG/` (with background) ·
  `Transparent/PNG` `Transparent/SVG` `Transparent/PDF`.
- **Raster quality** @2× (`LOGO_EXPORT_SCALE`), JPEG q95 4:4:4. SVG/PDF vector.
- **Icon set is OPTIONAL:** no icon tagged/marked and no named icon layer →
  logo set only. Never auto-ship an icon the CSR didn't ask for.
- **Masters carry ONLY the selected artboard** (`masters.py` extracts the chosen
  PDF page and strips the native PGF blob so Adobe honors one artboard; EPS is
  re-rendered from that page). Never recolored; RGB only.
- **Out of scope → flag "manual," refuse (no partial zip):** mesh/freeform
  gradients, embedded raster `<image>`, filters/shadows, in-art transparency,
  spot colors, live (un-outlined) text, integrated lockups.

---

## 4. Multiple files + tag-each-artboard (current feature)
The CSR can **upload several files at once** and see **every artboard of every
file** on the next page, then **tag** one as the **Logo** lockup and (optionally)
one as the **Icon** — they may live on different artboards or even different
files. One package is generated from the two tagged sources.

- `POST /ingest` accepts `files: UploadFile[]` (back-compat single `ai`/`eps`
  still works). Each artboard gets a **global index** across all files; the
  response carries `files[]` and per-artboard `file_index`/`file_name`/`page`.
  A `sources.json` map is written per job so `/generate` can find each artboard's
  source file (for masters) and page.
- `POST /generate` takes `logo_artboard` + `icon_artboard` (global indices) +
  `logo_box` + `icon_box`. Back-compat: `artboard` + `selection_box` still work.
- Icon routing: separate icon artboard → its own SVG + `icon_box`; icon within
  the logo artboard (or untagged) → `selection_box` within the logo.
- Frontend: `Uploader.jsx` (multi-file), `ArtboardTagger.jsx` (tag Logo/Icon per
  artboard, grouped by file), `App.jsx` (state `logoArtboard`/`iconArtboard`;
  a second preview appears when the icon is a separate artboard). A single file
  with one artboard auto-tags it as the logo and skips the tag step.

---

## 5. Architecture invariants (subtle things that WILL break if changed)
- **Coordinate mapping:** screen↔SVG goes through the **injected artwork SVG's
  own `getScreenCTM()`** (`SvgPreview.jsx`) — the browser's ground-truth
  transform for what it rendered. Never hand-roll rect math or use a separate
  viewBox guess. A box drawn on the mark must map to the mark server-side.
- **viewBox normalization at ingest** (`WorkingSVG._ensure_viewbox`): some
  poppler builds emit width/height but no viewBox, and the px scale varies
  host-to-host. A viewBox is derived from width/height AND width/height are
  pinned to unitless numbers, so the served SVG, the `viewbox` prop, svgelements
  geometry, and the browser share ONE space. (The nastiest past bug: live
  `width="880.91pt"` made svgelements geometry 1.333× larger than the viewBox —
  "worked locally, failed on the live server." Fixed here.)
- **Text as `<use>`:** pdf2svg emits text as hundreds of `<use>` of glyph
  outlines in `<defs>` — invisible to selection/geometry yet still painted.
  `svgutil.flatten_uses` (run in `WorkingSVG.__init__`) inlines them into tagged
  paths so they can be measured, selected, and pruned.
- **pdf2svg quirks:** colors arrive as `rgb(%, %, %)` (normalize before luminance
  or it crashes); coords scale pt→px (~0.75); each artboard = a PDF page.
- **Source page background rect** (Illustrator/pdf2svg adds one) is detected and
  **excluded** from artwork/bbox/colors so the logo isn't tiny/off-center.
- **Brand colors:** rank by area; brand-A = darkest chromatic, brand-B = most
  vivid. Neutrals excluded by **saturation** (dark-but-chromatic navy stays a
  brand color; near-black/gray artifacts don't).
- **Selection is authoritative & loud:** a drawn box that covers no artwork →
  `/generate` returns **422 `box_miss`** (job kept alive for a retry), echoing the
  received box vs artwork extent so a screenshot is a full diagnosis. Never
  silently ship the wrong thing, never auto-carve an icon out of a wordmark.

---

## 6. Hard-won lessons (bugs fixed — do not reintroduce)
- **Never recolor the white primary.** (PACK/Aurora.) Guard is skipped on white.
- **Slot 02 "same on dark" is canvas-only** (`keep`), so layered/offset sibling
  strokes don't get treated as each other's backdrop and blacked out.
- **A backdrop must be ≥ 2.5× larger** to count as detail-on-shape; sibling
  strokes of similar size are judged against the canvas.
- **pt→px svgelements scaling** — pin width/height to unitless viewBox numbers.
- **Validate on the LIVE server and across MANY logos**, not one file locally.
  Past regressions hid because only one file was checked.
- **Don't over-engineer the recolor.** The owner's recipe is explicit and mostly
  deterministic; the clever adaptive guard caused most of the failures.

---

## 7. AI segmentation (optional, opt-in)
`POST /segment` renders the chosen artboard and asks **Claude vision
(`claude-fable-5`, env `LOGO_AI_MODEL`)** to propose editable logo/icon boxes —
active only when `ANTHROPIC_API_KEY` is set; any failure falls back to the
geometric `selection.auto_segment`. It's a **suggestion only**; the CSR reviews.
`source` in the response is `"ai" | "geometry" | "none"`.

---

## 8. Deploy & ops
- **Render**, Docker (`Dockerfile` multi-stage: builds the Vite frontend, runs
  FastAPI serving UI + API from one origin), blueprint `render.yaml`, honors
  `$PORT`, `healthCheckPath: /health`, `autoDeploy: true` from `main`.
- **Plan is `free`** → the service **sleeps after ~15 min idle**; the next visit
  cold-starts (~1 min) showing Render's "onrender" loading page (served by
  Render before our app boots — cannot be restyled).
- **Cold-start fix in place:** `.github/workflows/keep-warm.yml` pings `/health`
  every 10 min to keep it awake (free + unlimited on this public repo). GitHub's
  scheduler can lag, so rare cold starts are still possible.
- **Permanent fix (optional, ~$7/mo):** set `render.yaml` `plan: starter` →
  always-on, more RAM (faster generation), keep-warm no longer needed.

---

## 9. Dev / test / workflow
```bash
./scripts/setup.sh                                    # toolchain + venv + npm
.venv/bin/python -m pytest backend                    # 119 tests must stay green
.venv/bin/uvicorn app.main:app --app-dir backend --reload   # API + serves frontend/dist
cd frontend && npm run dev                            # UI (proxies API)
cd frontend && npm run build                          # production bundle
```
- Develop on `claude/affectionate-euler-sFiaC`; to ship, merge → `main` and push
  (Render auto-deploys). Owner's standing instruction: ship without asking to
  merge; keep tests green.
- Real reference logos are **not** committed (uploaded per-session). Validate by
  ingesting a real `.ai` end-to-end and eyeballing a contact sheet of all slides.

---

## 10. Current status & open items
**Foundation shipped by THIS chat (all on `main`):** the 6-slide trained recipe;
multiple-file upload; tag-each-artboard as Logo/Icon across artboards and files;
keep-warm workflow; tests green; `CLAUDE.md` updated.

**Since built further on `main` by the parallel chat (see the ⚠ note up top):**
authored-background detection + "lead with the authored background"; light-but-
saturated field detection; two-tone icon/text split; named-lockup tagging + a
Text (typography-only) set; deep-shade fallback removed. Treat `CLAUDE.md` +
`git log` on `main` as the current truth.

**Known/open:**
- Multi-file UI was verified by build + full API smoke tests, **not** a real
  browser click-through (no browser in that environment) — worth a manual pass.
- When the logo's darkest shade **is** a brand color (e.g. navy+red), slot 02 and
  slot 03 can both land on that dark color — minor redundancy, acceptable, refine
  later.
- 1-color / neutral / 3+-color logos use the adaptive fallback on brand fields;
  the owner said "there will be exceptions we learn over time."
- Render is on the free plan (keep-warm mitigates; paid Starter is the clean fix).

**How to keep improving the recipe:** the owner trains by example — when a
generated package is wrong, they explain the exact rule. Encode the rule, add a
test, validate on the real file with a visual contact sheet, then ship.
