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
  const [logoBox, setLogoBox] = useState(null); // logo region (carve out a bento)
  const [iconBox, setIconBox] = useState(null);  // icon region
  const [removed, setRemoved] = useState([]);
  const [mark, setMark] = useState("icon"); // 'logo' | 'icon' | 'named' — active tool
  const [suggestion, setSuggestion] = useState(null); // auto-detected boxes + note
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
    setRemoved([]);
    setManual(null);
    setSuggestion(null);
    let lb = null, ib = null;
    if (index != null) {
      const b = r.artboards.find((x) => x.index === index);
      const s = b.suggestion;
      if (s) {
        // Pre-fill the auto-detected logo/icon regions — editable suggestions.
        lb = s.logo_box;
        ib = s.icon_box;
        setSuggestion(s);
      }
      // Named layers win as the icon source unless we detected a sharper box.
      setMark(b.named_selection && !(s && s.icon_box) ? "named" : "icon");
      if (!b.supported) setManual({ reasons: b.reasons });
    }
    setLogoBox(lb);
    setIconBox(ib);
  }

  async function handleGenerate() {
    setBusy(true);
    setError(null);
    try {
      const blob = await generate({
        job_id: result.job_id,
        brand,
        artboard: chosen,
        logo_box: logoBox,
        selection_box: mark === "named" ? null : iconBox,
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
    setLogoBox(null);
    setIconBox(null);
    setRemoved([]);
    setManual(null);
    setSuggestion(null);
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
            <StepHeader n="2a" title="Mark logo & icon" />
            {result.artboard_count > 1 && (
              <button
                onClick={() => setChosen(null)}
                className="mb-2 text-xs text-pulse-600 underline"
              >
                ← {active.label} · change artboard
              </button>
            )}
            <MarkTools
              mark={mark}
              setMark={setMark}
              hasNamed={!!active.named_selection}
              logoBox={logoBox}
              iconBox={iconBox}
              clearLogo={() => setLogoBox(null)}
              clearIcon={() => setIconBox(null)}
            />
            {suggestion && (logoBox || iconBox) && (
              <div className="mb-2 flex items-start justify-between gap-3 rounded-lg border border-pulse-200 bg-pulse-50 px-3 py-2 text-xs text-pulse-700">
                <span>
                  <span className="font-semibold">Auto-detected.</span> {suggestion.note}
                </span>
                <button
                  onClick={() => { setLogoBox(null); setIconBox(null); setSuggestion(null); }}
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
              workingSvg={active.working_svg}
              viewbox={active.viewbox}
              logoBox={logoBox}
              iconBox={iconBox}
              active={mark === "named" ? null : mark}
              onBox={(b) => (mark === "logo" ? setLogoBox(b) : setIconBox(b))}
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
                className="w-full rounded-md bg-pulse-500 py-2.5 font-medium text-white disabled:opacity-40"
              >
                {busy
                  ? "Building package…"
                  : mark !== "named" && !iconBox
                  ? "Generate logo files (no icon) →"
                  : "Generate & download .zip"}
              </button>
              {mark !== "named" && !iconBox && (
                <p className="mt-2 text-xs text-slate-500">
                  No icon box drawn — the package will contain the logo set only
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
        HaseebMadeIt · Logo Package Engine — upload → zip
      </footer>
    </div>
  );
}

function MarkTools({ mark, setMark, hasNamed, logoBox, iconBox, clearLogo, clearIcon }) {
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
        <Tool id="icon" label="Icon" dot="bg-emerald-500" />
        {hasNamed && <Tool id="named" label="Detected layer" />}
      </div>
      {logoBox && (
        <button onClick={clearLogo} className="text-xs text-slate-400 underline hover:text-slate-600">
          clear logo
        </button>
      )}
      {iconBox && (
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
