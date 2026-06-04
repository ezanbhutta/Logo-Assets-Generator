# Reference fixture (ground truth)

Per `BUILD_SPEC.md` §0/§10, the ground-truth package
`Fire_Systems_PNG_Limited_Files.zip` should be unzipped **here**
(`fixtures/reference/`). Every engine output is meant to match this package's
folder tree, file naming, and visual treatment.

**The reference zip was not attached to this build session**, so it is not
committed. The engine was instead built to the spec's *decoded* facts (§10):

- reusable color classes — red `#ec1c24`, navy `#112630`, white `#fff`;
  black = SVG default (no fill)
- two marks: **Logo** (full lockup) and **Icon** (bare flame)
- with-bg set: 5 treatments each for Icon and Logo; transparent set: Icon ×3,
  Logo ×4; single `.ai` + `.eps` at root

A representative stand-in lives in `fixtures/synthetic/` (a 2-color solid logo,
a gradient logo, and an out-of-scope file) and drives the test suite.

## To validate against the real fixture

1. Drop `Fire_Systems_PNG_Limited_Files.zip` in this folder and unzip it.
2. Feed the fixture's primary `.ai` through the engine (`/ingest` → `/generate`).
3. Compare the produced tree/naming to the unzipped reference (the with-bg
   artboards are **1920×1080** here per the locked spec, vs the fixture's
   square boards — treatment logic, recipe counts, naming, and the transparent
   set still match).
