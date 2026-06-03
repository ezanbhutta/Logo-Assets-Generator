import { useState } from "react";
import Uploader from "./components/Uploader.jsx";
import SvgPreview from "./components/SvgPreview.jsx";
import ColorConfirm from "./components/ColorConfirm.jsx";
import { ingest, generate, downloadBlob } from "./api.js";

export default function App() {
  const [result, setResult] = useState(null);
  const [brand, setBrand] = useState("");
  const [box, setBox] = useState(null);
  const [removed, setRemoved] = useState([]);
  const [mode, setMode] = useState("box"); // 'box' | 'named'
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  async function handleIngest(payload) {
    setBusy(true);
    setError(null);
    try {
      const r = await ingest(payload);
      setResult(r);
      setBrand(r.brand);
      setMode(r.named_selection ? "named" : "box");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerate() {
    setBusy(true);
    setError(null);
    try {
      const blob = await generate({
        job_id: result.job_id,
        brand,
        selection_box: mode === "box" ? box : null,
        removed_colors: removed,
        brand_a: result.brand_a,
        brand_b: result.brand_b,
      });
      downloadBlob(blob, `${brand} Files.zip`);
      setDone(true);
    } catch (e) {
      if (e.manual) setResult({ ...result, classification: "manual", reasons: e.reasons });
      else setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setResult(null);
    setBox(null);
    setRemoved([]);
    setDone(false);
    setError(null);
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-brand-navy">Logo Package Engine</h1>
        <p className="text-sm text-slate-500">
          Upload a primary logo → mark the icon → confirm colors → download the full package.
        </p>
      </header>

      {error && (
        <Banner tone="error" onClose={() => setError(null)}>{error}</Banner>
      )}

      {!result && (
        <Card>
          <Uploader onIngest={handleIngest} busy={busy} />
        </Card>
      )}

      {result && result.classification === "manual" && (
        <ManualFlag reasons={result.reasons} onReset={reset} />
      )}

      {result && result.classification !== "manual" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <StepHeader n="2a" title="Mark the icon" />
            <SelectionModeToggle
              hasNamed={!!result.named_selection}
              mode={mode}
              setMode={setMode}
            />
            {mode === "box" && (
              <p className="mb-2 text-xs text-slate-500">
                Drag one box around the icon. Everything outside becomes the wordmark.
              </p>
            )}
            <SvgPreview
              workingSvg={result.working_svg}
              viewbox={result.viewbox}
              box={box}
              onBox={setBox}
              enabled={mode === "box"}
            />
            {result.named_selection?.overlap_warning && (
              <Banner tone="warn">
                Icon and wordmark overlap heavily — if the mark is fused into a
                letter, this lockup may need manual handling (§9).
              </Banner>
            )}
          </Card>

          <Card>
            <StepHeader n="2b" title="Confirm colors" />
            <ColorConfirm
              result={result}
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
                converter: {result.converter} · {result.is_gradient ? "gradient" : "solid"} recipes
              </div>
              <button
                disabled={busy || (mode === "box" && !box)}
                onClick={handleGenerate}
                className="w-full rounded-md bg-brand-red py-2.5 font-medium text-white disabled:opacity-40"
              >
                {busy ? "Building package…" : "Generate & download .zip"}
              </button>
              {mode === "box" && !box && (
                <p className="mt-2 text-xs text-amber-600">Draw the icon box first.</p>
              )}
              {done && (
                <Banner tone="ok">
                  Package downloaded as <strong>{brand} Files.zip</strong>.{" "}
                  <button className="underline" onClick={reset}>Start another</button>
                </Banner>
              )}
            </div>
          </Card>
        </div>
      )}
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
  <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">{children}</div>
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
