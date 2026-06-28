import { useState } from "react";
import Uploader from "./components/Uploader.jsx";
import SvgPreview from "./components/SvgPreview.jsx";
import ColorConfirm from "./components/ColorConfirm.jsx";
import ArtboardTagger from "./components/ArtboardTagger.jsx";
import TopBar from "./components/TopBar.jsx";
import Steps from "./components/Steps.jsx";
import { ingest, generate, segment, downloadBlob } from "./api.js";

export default function App() {
  const [result, setResult] = useState(null);
  // The CSR tags two roles across all artboards/files (global indices).
  const [logoArtboard, setLogoArtboard] = useState(null);
  const [iconArtboard, setIconArtboard] = useState(null);
  const [tagged, setTagged] = useState(false); // has the CSR finished the tag step?
  const [brand, setBrand] = useState("");
  const [logoBox, setLogoBox] = useState(null);   // logo region within the logo artboard
  const [iconBox, setIconBox] = useState(null);    // icon region within the icon source
  const [removed, setRemoved] = useState([]);
  const [mark, setMark] = useState("icon"); // 'logo' | 'icon' | 'named' — logo-preview tool
  const [suggestion, setSuggestion] = useState(null);
  const [usedSuggestion, setUsedSuggestion] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [detectNote, setDetectNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [manual, setManual] = useState(null);
  const [done, setDone] = useState(false);

  const boardAt = (i) =>
    result && i != null ? result.artboards.find((b) => b.index === i) : null;
  const logoBoard = boardAt(logoArtboard);
  // a SEPARATE icon artboard (distinct from the logo); null when the icon is
  // inside the logo artboard or untagged.
  const iconBoard =
    iconArtboard != null && iconArtboard !== logoArtboard ? boardAt(iconArtboard) : null;
  const iconInLogo = iconArtboard == null || iconArtboard === logoArtboard;

  async function handleIngest(payload) {
    setBusy(true);
    setError(null);
    try {
      const r = await ingest(payload);
      setResult(r);
      setBrand(r.brand);
      resetSelection();
      // suggest the engine's primary as the logo; single artboard -> skip tagging
      setLogoArtboard(r.primary_index);
      setIconArtboard(null);
      setTagged(r.artboard_count === 1);
      if (r.artboard_count === 1) primeBoard(r, r.primary_index);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function resetSelection() {
    setRemoved([]);
    setManual(null);
    setSuggestion(null);
    setUsedSuggestion(false);
    setDetectNote("");
    setLogoBox(null);
    setIconBox(null);
  }

  // Prepare the marking step for a chosen logo artboard: load its auto-detected
  // boxes (computed server-side in the artwork's own space) and pick a tool.
  function primeBoard(r, index) {
    const b = r.artboards.find((x) => x.index === index);
    if (!b) return;
    if (b.suggestion) {
      setSuggestion(b.suggestion);
      const { logo_box, icon_box, note } = b.suggestion;
      if (logo_box) setLogoBox(logo_box);
      if (icon_box) setIconBox(icon_box);
      if (logo_box || icon_box) {
        setUsedSuggestion(true);
        setDetectNote(note || "");
      }
    }
    setMark(b.named_selection ? "named" : "icon");
    if (!b.supported) setManual({ reasons: b.reasons });
  }

  function onTag(role, index) {
    if (role === "logo") {
      setLogoArtboard((cur) => (cur === index ? null : index));
    } else {
      setIconArtboard((cur) => (cur === index ? null : index));
    }
  }

  function onContinue() {
    if (logoArtboard == null) return;
    resetSelection();
    primeBoard(result, logoArtboard);
    setTagged(true);
  }

  // Auto-detect on the LOGO artboard (Claude vision when a key is set; geometric
  // fallback otherwise).
  async function applySuggestion() {
    if (detecting || logoArtboard == null) return;
    setDetecting(true);
    let s = await segment({ job_id: result.job_id, artboard: logoArtboard });
    setDetecting(false);
    if (!s || (!s.logo_box && !s.icon_box)) {
      s = suggestion
        ? { ...suggestion, source: "geometry" }
        : s || { logo_box: null, icon_box: null, note: "", source: "none" };
    }
    setLogoBox(s.logo_box || null);
    if (iconInLogo) setIconBox(s.icon_box || null);
    if (s.icon_box && iconInLogo) setMark("icon");
    else if (s.logo_box) setMark("logo");
    setDetectNote(
      s.note || (s.logo_box || s.icon_box ? "" : "Nothing to auto-detect — draw the boxes by hand.")
    );
    setUsedSuggestion(true);
  }

  async function handleGenerate() {
    setBusy(true);
    setError(null);
    try {
      const blob = await generate({
        job_id: result.job_id,
        brand,
        logo_artboard: logoArtboard,
        icon_artboard: iconArtboard,
        logo_box: logoBox,
        // icon_box is relative to whichever artboard holds the icon (the backend
        // routes it). When the icon is a named layer in the logo, send no box.
        icon_box: iconInLogo && mark === "named" ? null : iconBox,
        removed_colors: removed,
        brand_a: logoBoard.brand_a,
        brand_b: logoBoard.brand_b,
      });
      downloadBlob(blob, `${brand} Files.zip`);
      setDone(true);
    } catch (e) {
      if (e.manual) setManual({ reasons: e.reasons });
      else setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setResult(null);
    setLogoArtboard(null);
    setIconArtboard(null);
    setTagged(false);
    resetSelection();
    setDetecting(false);
    setDone(false);
    setError(null);
  }

  const currentStep = done ? 4 : !result ? 1 : !tagged ? 2 : 3;
  const showMark = result && tagged && logoBoard;

  return (
    <div className="min-h-full">
      <TopBar onNew={reset} showNew={!!result} />

      <div className="pt-7">
        <Steps current={currentStep} />
      </div>

      <main className="mx-auto max-w-6xl px-4 pb-20">
        <div className="mb-6">
          <h1 className="text-xl font-bold tracking-tight text-slate-800">
            Logo Package Engine
          </h1>
          <p className="text-sm text-slate-500">
            Upload your files → tag the Logo & Icon → mark regions → confirm colors → download.
          </p>
        </div>

        {error && (
          <Banner tone="error" onClose={() => setError(null)}>{error}</Banner>
        )}

        {!result && (
          <Card>
            <Uploader onIngest={handleIngest} busy={busy} />
          </Card>
        )}

        {result && !tagged && (
          <ArtboardTagger
            artboards={result.artboards}
            files={result.files}
            primaryIndex={result.primary_index}
            logoArtboard={logoArtboard}
            iconArtboard={iconArtboard}
            onTag={onTag}
            onContinue={onContinue}
          />
        )}

        {showMark && manual && <ManualFlag reasons={manual.reasons} onReset={reset} />}

        {showMark && !manual && (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <StepHeader n="2a" title="Mark logo & icon" />
              {result.artboard_count > 1 && (
                <button
                  onClick={() => setTagged(false)}
                  className="mb-2 text-xs text-pulse-600 underline"
                >
                  ← {logoBoard.label} · change tags
                </button>
              )}
              <MarkTools
                mark={mark}
                setMark={setMark}
                hasNamed={!!logoBoard.named_selection}
                hasIconTool={iconInLogo}
                logoBox={logoBox}
                iconBox={iconBox}
                clearLogo={() => setLogoBox(null)}
                clearIcon={() => setIconBox(null)}
              />
              {!usedSuggestion && !logoBox && !iconBox && (
                <button
                  onClick={applySuggestion}
                  disabled={detecting}
                  className="mb-2 inline-flex items-center gap-1.5 rounded-lg border border-pulse-200 bg-pulse-50 px-3 py-1.5 text-xs font-medium text-pulse-700 hover:bg-pulse-100 disabled:opacity-60"
                >
                  {detecting ? (
                    <svg width="13" height="13" viewBox="0 0 24 24" className="animate-spin" fill="none">
                      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" strokeOpacity="0.25" />
                      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                    </svg>
                  ) : (
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M13 2L4.5 13.5H11l-1 8.5 9-12H12l1-8z" />
                    </svg>
                  )}
                  {detecting ? "Reading the artboard…" : "Auto-detect logo & icon"}
                </button>
              )}
              {usedSuggestion && (logoBox || iconBox) && (
                <div className="mb-2 flex items-start justify-between gap-3 rounded-lg border border-pulse-200 bg-pulse-50 px-3 py-2 text-xs text-pulse-700">
                  <span>
                    <span className="font-semibold">Auto-detected.</span> {detectNote}
                  </span>
                  <button
                    onClick={() => { setLogoBox(null); setIconBox(null); setUsedSuggestion(false); setDetectNote(""); }}
                    className="shrink-0 text-pulse-400 underline hover:text-pulse-600"
                  >
                    clear
                  </button>
                </div>
              )}
              <p className="mb-2 text-xs text-slate-500">
                {mark === "logo"
                  ? "Drag a box around the actual logo — use this for a brand-sheet / bento; everything outside is ignored."
                  : mark === "icon"
                  ? "Drag a box around the icon (optional). It must sit inside the logo region."
                  : "Using the file's detected Icon layer."}
              </p>
              <SvgPreview
                workingSvg={logoBoard.working_svg}
                viewbox={logoBoard.viewbox}
                logoBox={logoBox}
                iconBox={iconInLogo ? iconBox : null}
                active={mark === "named" ? null : mark === "icon" && !iconInLogo ? "logo" : mark}
                onBox={(b) => (mark === "logo" ? setLogoBox(b) : iconInLogo ? setIconBox(b) : null)}
              />
              {logoBoard.named_selection?.overlap_warning && (
                <Banner tone="warn">
                  Icon and wordmark overlap heavily — if the mark is fused into a
                  letter, this lockup may need manual handling (§9).
                </Banner>
              )}

              {iconBoard && (
                <div className="mt-5 border-t border-slate-200 pt-4">
                  <div className="mb-1 flex items-center gap-1.5 text-sm font-medium text-slate-700">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" /> Icon source ·{" "}
                    {iconBoard.label}
                  </div>
                  <p className="mb-2 text-xs text-slate-500">
                    The whole artboard is the icon. Drag a box only to crop a region of it.
                  </p>
                  <SvgPreview
                    workingSvg={iconBoard.working_svg}
                    viewbox={iconBoard.viewbox}
                    logoBox={null}
                    iconBox={iconBox}
                    active="icon"
                    onBox={(b) => setIconBox(b)}
                  />
                  {iconBox && (
                    <button
                      onClick={() => setIconBox(null)}
                      className="mt-1 text-xs text-slate-400 underline hover:text-slate-600"
                    >
                      clear icon region (use whole artboard)
                    </button>
                  )}
                </div>
              )}
            </Card>

            <Card>
              <StepHeader n="2b" title="Confirm colors" />
              <ColorConfirm
                result={logoBoard}
                removed={removed}
                onToggle={(c) =>
                  setRemoved((r) => (r.includes(c) ? r.filter((x) => x !== c) : [...r, c]))
                }
              />

              <div className="mt-6 border-t border-slate-200 pt-5">
                <StepHeader n="3" title="Generate package" />
                <label className="mb-3 block text-sm">
                  <span className="mb-1 block font-medium text-slate-600">Brand name</span>
                  <input
                    className="w-full rounded-md border border-slate-300 px-3 py-2"
                    value={brand}
                    onChange={(e) => setBrand(e.target.value)}
                  />
                </label>
                <div className="mb-3 text-xs text-slate-500">
                  converter: {result.converter} · {logoBoard.is_gradient ? "gradient" : "solid"} recipes
                  {iconBoard ? ` · icon from ${iconBoard.label}` : ""}
                </div>
                <button
                  disabled={busy}
                  onClick={handleGenerate}
                  className="w-full rounded-md bg-pulse-500 py-2.5 font-medium text-white disabled:opacity-40"
                >
                  {busy
                    ? "Building package…"
                    : !hasIcon(iconInLogo, iconBox, iconBoard, mark)
                    ? "Generate logo files (no icon) →"
                    : "Generate & download .zip"}
                </button>
                {!hasIcon(iconInLogo, iconBox, iconBoard, mark) && (
                  <p className="mt-2 text-xs text-slate-500">
                    No icon tagged or marked — the package will contain the logo set only
                    {logoBox ? " (from the marked logo region)" : ""}.
                  </p>
                )}
                {done && (
                  <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                    <p className="text-sm text-emerald-800">
                      ✓ Downloaded <strong>{brand} Files.zip</strong>.
                    </p>
                    <button
                      onClick={reset}
                      className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-pulse-500 px-3.5 py-2 text-sm font-medium text-white hover:bg-pulse-600"
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
                        <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
                      </svg>
                      Generate new
                    </button>
                  </div>
                )}
              </div>
            </Card>
          </div>
        )}
      </main>

      <footer className="border-t border-slate-200 py-5 text-center text-xs text-slate-400">
        HaseebMadeIt · Logo Package Engine — upload → zip · build {typeof __BUILD_STAMP__ !== "undefined" ? __BUILD_STAMP__ : "dev"}
      </footer>
    </div>
  );
}

// An icon ships when a separate icon artboard is tagged, OR an icon box/named
// layer is marked inside the logo artboard.
function hasIcon(iconInLogo, iconBox, iconBoard, mark) {
  if (iconBoard) return true;               // separate tagged icon artboard
  if (!iconInLogo) return true;             // (defensive) icon on another board
  return mark === "named" || !!iconBox;     // icon marked within the logo
}

function MarkTools({ mark, setMark, hasNamed, hasIconTool, logoBox, iconBox, clearLogo, clearIcon }) {
  const Tool = ({ id, label, dot }) => (
    <button
      onClick={() => setMark(id)}
      className={`inline-flex items-center gap-1.5 rounded px-3 py-1 ${
        mark === id ? "bg-pulse-500 text-white" : "text-slate-600"
      }`}
    >
      {dot && <span className={`h-2 w-2 rounded-full ${dot}`} />}
      {label}
    </button>
  );
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
      <div className="inline-flex rounded-md border border-slate-300 p-0.5">
        <Tool id="logo" label="Logo region" dot="bg-pulse-500" />
        {hasIconTool && <Tool id="icon" label="Icon" dot="bg-emerald-500" />}
        {hasNamed && <Tool id="named" label="Detected layer" />}
      </div>
      {logoBox && (
        <button onClick={clearLogo} className="text-xs text-slate-400 underline hover:text-slate-600">
          clear logo
        </button>
      )}
      {iconBox && hasIconTool && (
        <button onClick={clearIcon} className="text-xs text-slate-400 underline hover:text-slate-600">
          clear icon
        </button>
      )}
    </div>
  );
}

function ManualFlag({ reasons, onReset }) {
  return (
    <Card>
      <div className="space-y-3">
        <h2 className="text-lg font-semibold text-pulse-500">Route to manual</h2>
        <p className="text-sm text-slate-600">
          This logo can't be auto-packaged because it contains:
        </p>
        <ul className="list-inside list-disc text-sm text-slate-700">
          {(reasons || []).map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <p className="text-xs text-slate-500">
          No partial package is produced — these inputs need a designer (§9).
        </p>
        <button onClick={onReset} className="rounded-md bg-pulse-500 px-4 py-2 text-sm text-white">
          Start over
        </button>
      </div>
    </Card>
  );
}

const Card = ({ children }) => (
  <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm ring-1 ring-black/[0.02]">
    {children}
  </div>
);

const StepHeader = ({ n, title }) => (
  <div className="mb-3 flex items-center gap-2">
    <span className="grid h-6 w-6 place-items-center rounded-full bg-pulse-500 text-xs font-bold text-white">
      {n}
    </span>
    <h2 className="text-base font-semibold text-slate-700">{title}</h2>
  </div>
);

function Banner({ tone = "ok", children, onClose }) {
  const tones = {
    ok: "bg-green-50 text-green-800 border-green-200",
    error: "bg-red-50 text-red-800 border-red-200",
    warn: "bg-amber-50 text-amber-800 border-amber-200",
  };
  return (
    <div className={`mb-4 flex items-start justify-between gap-3 rounded-md border px-4 py-3 text-sm ${tones[tone]}`}>
      <div>{children}</div>
      {onClose && (
        <button onClick={onClose} className="text-lg leading-none">×</button>
      )}
    </div>
  );
}
