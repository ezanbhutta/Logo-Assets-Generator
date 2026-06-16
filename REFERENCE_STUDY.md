# Reference Study — what 18 real designer packages tell us

Evidence base for the engine's output standard. Built by analyzing every real
delivery package available (`/root/.claude/uploads/**`), not assumptions. This is
the ground truth `BUILD_SPEC.md` was missing at build time (the fixture was never
attached). Where this disagrees with earlier guesses, **the data wins**.

## Corpus (18 packages)
Eveline Campbell · Fahrschulzentrum · **Fire Systems PNG Limited** (the spec
fixture) · Got You Floored · LeadIn · MpCarney · **Orova Electronics** (gradient)
· PictureBond · **Pulse** (HaseebMadeIt house brand) · Sawaat · **Snoot** ·
Spice · Sway · Tays ×3 · Yundo · **Zytress** (multicolor).

Three tiers are visible:
- **Core logo/icon packages** (the engine's job): Fire, LeadIn, MpCarney, Orova,
  Tays, Zytress, Eveline, Fahrschulzentrum, Got You Floored, PictureBond.
- **Premium brand packages** (logo set **+** extras): Pulse, Snoot, Spice,
  Zytress — add brand guidelines, fonts, social kit, business card, iconography.
- **Single-deliverable** drops: Sawaat (only social covers), Yundo/Sway (one
  artboard), PictureBond (single Icon/Logo, no numbered set).

## 1. Artboard sizes (measured from the raster exports)
| Package | with-bg LOGO | with-bg ICON | Verdict |
|---|---|---|---|
| **Pulse** (house) | 7680×4320 (16:9) | **4320×4320 (square)** | logo 16:9, icon square |
| **Snoot** | 7680×4320 | **4320×4320** | logo 16:9, icon square |
| Orova | 3840×2160 | 3840×2160 | both 16:9 |
| Tays ×3 | 3840×2160 | 3840×2160 | both 16:9 |
| Fire, LeadIn, Zytress | square | square | both square |
| MpCarney | 2401×2400 | square | both square |

**Decision the owner already made — and the data backs it:** logo **16:9
(1920×1080)**, icon **square (1080×1080)**. This is exactly Pulse/Snoot, the house
brand. The engine already does this. ✔

## 2. Mark sizing inside the artboard (the real number, measured)
Binding side = the mark's longer dimension as a % of the canvas.

| | LOGO binding side | ICON binding side |
|---|---|---|
| Pulse (house) | 50% | **44%** |
| Orova | 65% | ~30% |
| Zytress | 60% | 35% |
| MpCarney | 64% | 31% |
| LeadIn | 56% | 29% |
| Fire | 50% | 29% |
| **range** | **50–65%** | **29–44%** |

- **Logo at 60%** sits right in the real range. ✔ (`SAFE_FRACTION = 0.60`)
- **Icon at 60% is too big.** Every reference — including Pulse, the house brand
  — puts the icon at **29–44%** (median ≈ 33%, Pulse 44%). At 60% the icon reads
  oversized/cramped versus the standard. **Recommend ICON ≈ 0.42** (matches the
  most generous reference, Pulse) — a separate `ICON_SAFE_FRACTION`.
- Everything is **center-balanced** (centroid at 0.5, 0.5). ✔

## 3. Treatment recipes (validated against the images)
**Solid 2-color (Fire), multicolor (Zytress), house brand (Pulse):**
| # | bg | mark |
|---|---|---|
| 01 | white | full color |
| 02 | brand-A (dark) | **adaptive** — every color that reads is kept; wordmark/failing colors → white |
| 03 | brand-B (vivid) | **adaptive** — on Pulse's own blue the mark goes white; Zytress's multicolor stays |
| 04 | white | all black (mono) |
| 05 | black | all white (mono) |

The engine's adaptive contrast guard reproduces this. ✔ (Zytress keeps the
green/teal/navy shield on both brand backgrounds — confirmed.)

**Gradient (Orova) — one correction needed:**
| # | bg | mark | engine now | fix |
|---|---|---|---|---|
| 01 | white | full gradient | ✔ | — |
| 02 | **rebuilt full-bleed gradient** | white knockout (hero) | ✔ | — |
| 03 | **black** | **WHITE** | keeps the gradient on black | **→ black/white** |
| 04 | white | black (mono) | ✔ | — |
| 05 | dark-stop solid | white | ✔ | — |

The "keep a vivid gradient on black" idea was mine; the designer standard (Orova)
is **white on black**. Revert slot 3 to white knockout.

## 4. Naming & folders (variation is real)
- Numbered, zero-padded `Icon 01` … `Logo 05`: the majority (Fire, LeadIn,
  MpCarney, Orova, Tays, Zytress, Eveline, Fahrschulzentrum, Got You Floored).
- `Icon 1` (single digit): Pulse, Snoot. `logo-01` (hyphen): Spice. → outliers.
- **Folder: `JPG` vs `JPEG`** is a genuine ~50/50 split (`JPG`: Fire, LeadIn,
  MpCarney, Pulse, Snoot, Spice, Fahrschulzentrum; `JPEG`: Tays, Orova, Got You
  Floored, Eveline, Zytress). The engine uses `JPEG` (owner's Tays standard). ✔
- Counts: with-bg **5+5**, transparent **3 icon + 4 logo** is the clear mode
  (Fire, Tays, Orova, Zytress, LeadIn…). Logo-only files (Eveline,
  Fahrschulzentrum) ship **5 logos, no icon**. ✔ matches the optional-icon rule.

## 5. Structure
- Single `.ai` (+ `.eps` when supplied) at root: the standard. ✔ (engine now
  carves the single selected artboard.)
- Per-variant EPS (Got You Floored, Spice) and AI/EPS-in-folders (Pulse, Snoot,
  Spice): **outliers**, correctly ignored.
- `.eps` is present in ~60% of packages; absent in Tays/Orova/Eveline/Got You
  Floored. The engine ships `.eps` only when uploaded. ✔

## 6. The "extras" (only in premium packages)
Not in the engine's scope today; appear in Pulse/Snoot/Spice/Zytress/Sawaat:
- **Social covers** (Facebook/LinkedIn/Twitter-X/YouTube) — Sawaat is *only*
  these; also in Snoot/Spice. A defined, repeatable artifact.
- Brand guidelines (`.ai`+`.pdf`), font files, business card, Instagram
  templates, profile picture, **iconography sets** (Zytress: 20 assets).
- These are designer-authored, brand-specific, or licensed — **not auto-
  generatable from one logo** (guidelines, fonts, custom iconography). Social
  covers and profile pictures *are* auto-generatable (logo on a sized canvas).

## 7. Gaps found in the current engine (evidence-backed)
1. **Icon oversized** — 60% vs the 29–44% reference standard. (sizing)
2. **Gradient slot 3** — keeps gradient on black; standard is white. (recipe)
3. **Icon not auto-detected on a combination mark** — Orova's gear-above-wordmark
   yields `auto_segment → None`, so no icon set; the designer package has one.
   (segmentation: the conservative heuristic misses a clear stacked emblem)
4. **Gradient brand-color detection** — Orova's palette came back as grays
   (#474747/#d9d9d9); the gradient stops (magenta→purple) never entered the
   brand colors. Low impact on gradient backgrounds (gradient/dark-stop are
   used) but wrong in the confirm-colors UI. (color detection)

## 8. Proposed system (calibrations, not a rewrite)
The architecture is sound. The data calls for **calibration + 2 corrections**:
- **A. Icon size** → `ICON_SAFE_FRACTION ≈ 0.42` (logo stays 0.60). [needs owner OK]
- **B. Gradient slot 3** → white knockout on black (match Orova). [clear fix]
- **C. Combination-mark icon** → detect a clear stacked/side emblem as the icon
  so combination marks ship an icon set without a manual draw. [clear improvement]
- **D. Gradient palette** → fold gradient stop colors into brand-color detection
  so the swatches/【brand-A/B】reflect the real hues. [clear fix]
- **E. (Optional scope) Social covers + profile picture** — the one extra that is
  truly auto-generatable from the logo, and appears as its own deliverable
  (Sawaat). Everything else (guidelines, fonts, iconography) is human-authored
  and stays out. [needs owner OK on scope]

---

# Color recoloring across backgrounds — the moves (guidelines + web research)

Studied the three real brand-guideline documents shipped in the packages
(**Pulse**, **Snoot**, **Zytress** — 94 pages), the delivered variation sets of
6 brands, and ~12 web sources on professional brand-guideline practice
(logome.ai, frontify, brandyhq, deBroome, Case Western, JHU, UConn, IxDF, et al.).
The rules converge. The headline: **a logo on a colored background is NOT
reflexively white or black — designers recolor it to the brand's OWN color that
reads best, and only fall back to white/black.**

## The decision a designer actually makes (the one rule)
For any background, pick the mark color that **reads best while staying in the
brand's scheme**, in this priority:
1. **Keep the mark's real colors** if they read on the background (contrast ≥ ~3:1
   for a graphic — WCAG). Multi-color marks stay full-color on brand backgrounds
   where the colors survive (Zytress shield on navy AND cyan; Pulse dots on navy).
2. **Swap a failing color to another BRAND color that reads** — in-scheme, never
   white-by-default. *MpCarney: on the gold background the mark becomes NAVY (the
   other brand color), not white.* *deBroome/Case Western: "favor the primary or
   secondary palette; determine which color is best for contrast."*
3. **White or black, last** — white on dark/saturated, black on light. ("Navy is
   changed to white on dark backgrounds.")
4. **Never tone-on-tone** — never a color on a too-similar color (the forbidden
   move in every guideline).

## The background palette designers pull from (not just white/black)
white · the **dark brand color** · the **vivid brand color** · **tints** of a
brand color (a lighter dilution, used when it raises contrast) · black. The mark
is recolored per the rule above for each.

## Per-archetype moves (from the delivered sets, validated visually)
- **Multi-color (Pulse, Zytress):** full-color on white · **full-color KEPT on the
  dark brand color** (only the wordmark goes white) · white knockout on the vivid
  brand color · mono black · mono white.
- **Two-color (Fire, MpCarney):** full on white · the mark recolored to the OTHER
  brand color on a brand background (Fire: split, icon keeps red / wordmark white
  on navy; MpCarney: **navy mark on the gold background**) · white on the vivid ·
  mono pair.
- **One-color (Snoot, vivid red):** red on white · **white knockout on the brand
  red** · **the red KEPT on BLACK** (a vivid color reads on black — a striking
  in-scheme variation) · mono white on black · mono black on white.
- **Gradient (Orova):** full gradient on white · white knockout on the rebuilt
  full-bleed gradient (hero) · white on black · black mono on white · white on the
  darkest-stop solid.

## How the engine maps (audit)
The engine's adaptive contrast guard implements rule 1–4 already: keep colors
that read, substitute to the nearest reading PALETTE color, white/black last,
never tone-on-tone. Validated: MpCarney-style navy-on-gold, Zytress multicolor
kept on two brand backgrounds. **One gap from the research:** a vivid one-color
brand should show its color **on black** (Snoot's red-on-black). The engine
previously used a deep shade background with white — a redundant, less striking
slot. Fixed: a one-color mark that reads on black now gets the **brand color on
black** variation; a dark one-color mark (won't read on black) keeps the shade.

## Sources
Local: Pulse/Snoot/Zytress brand guideline PDFs (shipped in the packages). Web:
logome.ai (logo variations), frontify & brandyhq (logo usage playbooks), deBroome
(brand color best-practices), Case Western / Johns Hopkins / UConn brand systems,
Interaction Design Foundation (brand guidelines). All converge on the rule above.
