import { useState } from "react";
import Uploader from "./components/Uploader.jsx";
import SvgPreview from "./components/SvgPreview.jsx";
import ColorConfirm from "./components/ColorConfirm.jsx";
import ArtboardChooser from "./components/ArtboardChooser.jsx";
import TopBar from "./components/TopBar.jsx";
import Steps from "./components/Steps.jsx";
import { ingest, generate, downloadBlob } from "./api.js";

export default function App() {
  const [result, setResult] = useState(null);
  const [chosen, setChosen] = useState(null); // selected artboard index
  const [brand, setBrand] = useState("");
  const [box, setBox] = useState(null);
  const [removed, setRemoved] = useState([]);
  const [mode, setMode] = useState("box"); // 'box' | 'named'
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [manual, setManual] = useState(null); // {reasons} when active board is out of scope
  const [done, setDone] = useState(false);

  // The active artboard (the chosen primary logo) drives the rest of the flow.
  // `chosen` is the artboard's page index (.index), not a list position.
  const active =
    result && chosen != null
      ? result.artboards.find((b) => b.index === chosen)
      : null;

  async function handleIngest(payload) {
    setBusy(true);
    setError(null);
    try {
      const r = await ingest(payload);
      setResult(r);
      setBrand(r.brand);
      // Single artboard -> proceed straight away; multiple -> force a choice.
      pickArtboard(r, r.artboard_count === 1 ? r.primary_index : null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function pickArtboard(r, index) {
    setChosen(index);
    setBox(null);
    setRemoved([]);
    setManual(null);
    if (index != null) {
      const b = r.artboards.find((x) => x.index === index);
      setMode(b.named_selection ? "named" : "box");
      if (!b.supported) setManual({ reasons: b.reasons });
    }
  }

  async function handleGenerate() {
    setBusy(true);
    setError(null);
    try {
      const blob = await generate({
        job_id: result.job_id,
        brand,
        artboard: chosen,
        selection_box: mode === "box" ? box : null,
        removed_colors: removed,
        brand_a: active.brand_a,
        brand_b: active.brand_b,
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
    setChosen(null);
    setBox(null);
    setRemoved([]);
    setManual(null);
    setDone(false);
    setError(null);
  }

  const currentStep = done ? 4 : !result ? 1 : chosen == null ? 2 : 3;

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
            Upload a primary logo → pick the artboard → mark the icon → confirm colors → download.
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

      {result && chosen == null && (
        <ArtboardChooser
          artboards={result.artboards}
          primaryIndex={result.primary_index}
          onPick={(i) => pickArtboard(result, i)}
        />
      )}

      {active && manual && (
        <ManualFlag reasons={manual.reasons} onReset={reset} />
      )}

      {active && !manual && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <StepHeader n="2a" title="Mark the icon" />
            {result.artboard_count > 1 && (
              <button
                onClick={() => setChosen(null)}
                className="mb-2 text-xs text-brand-navy underline"
              >
                ← {active.label} · change artboard
              </button>
            )}
            <SelectionModeToggle
              hasNamed={!!active.named_selection}
              mode={mode}
              setMode={setMode}
            />
            {mode === "box" && (
              <p className="mb-2 text-xs text-slate-500">
                Drag one box around the icon to also get the icon set.{" "}
                <span className="text-slate-400">Optional</span> — skip it and only
                the logo design files are generated.
              </p>
            )}
            <SvgPreview
              workingSvg={active.working_svg}
              viewbox={active.viewbox}
              box={box}
              onBox={setBox}
              enabled={mode === "box"}
            />
            {active.named_selection?.overlap_warning && (
              <Banner tone="warn">
                Icon and wordmark overlap heavily — if the mark is fused into a
                letter, this lockup may need manual handling (§9).
              </Banner>
            )}
          </Card>

          <Card>
            <StepHeader n="2b" title="Confirm colors" />
            <ColorConfirm
              result={active}
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
                converter: {result.converter} · {active.is_gradient ? "gradient" : "solid"} recipes
              </div>
              <button
                disabled={busy}
                onClick={handleGenerate}
                className="w-full rounded-md bg-brand-red py-2.5 font-medium text-white disabled:opacity-40"
              >
                {busy
                  ? "Building package…"
                  : mode === "box" && !box
                  ? "Generate logo files (no icon) →"
                  : "Generate & download .zip"}
              </button>
              {mode === "box" && !box && (
                <p className="mt-2 text-xs text-slate-500">
                  No icon box drawn — the package will contain the logo set only.
                </p>
              )}
              {done && (
                <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                  <p className="text-sm text-emerald-800">
                    ✓ Downloaded <strong>{brand} Files.zip</strong>.
                  </p>
                  <button
                    onClick={reset}
                    className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-brand-navy px-3.5 py-2 text-sm font-medium text-white hover:bg-[#1c3d4f]"
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
        HaseebMadeIt · Logo Package Engine — upload → zip
      </footer>
    </div>
  );
}

function SelectionModeToggle({ hasNamed, mode, setMode }) {
  return (
    <div className="mb-3 inline-flex rounded-md border border-slate-300 p-0.5 text-sm">
      {hasNamed && (
        <button
          onClick={() => setMode("named")}
          className={`rounded px-3 py-1 ${mode === "named" ? "bg-brand-navy text-white" : "text-slate-600"}`}
        >
          Detected Icon layer
        </button>
      )}
      <button
        onClick={() => setMode("box")}
        className={`rounded px-3 py-1 ${mode === "box" ? "bg-brand-navy text-white" : "text-slate-600"}`}
      >
        Draw a box
      </button>
    </div>
  );
}

function ManualFlag({ reasons, onReset }) {
  return (
    <Card>
      <div className="space-y-3">
        <h2 className="text-lg font-semibold text-brand-red">Route to manual</h2>
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
        <button onClick={onReset} className="rounded-md bg-brand-navy px-4 py-2 text-sm text-white">
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
    <span className="grid h-6 w-6 place-items-center rounded-full bg-brand-navy text-xs font-bold text-white">
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
