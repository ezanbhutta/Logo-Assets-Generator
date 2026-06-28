import { useState } from "react";

// Step 1: Brand name + upload one or MORE files (.ai/.eps/.pdf/.svg). The logo
// lockup and the icon may live on different artboards or even different files —
// drop them all here and tag each artboard's role on the next page (§3.1-3.3).
export default function Uploader({ onIngest, busy }) {
  const [files, setFiles] = useState([]);
  const [brand, setBrand] = useState("");

  function addFiles(list) {
    const incoming = Array.from(list || []);
    if (!incoming.length) return;
    setFiles((cur) => {
      // de-dupe by name+size; keep order added
      const seen = new Set(cur.map((f) => f.name + f.size));
      const merged = [...cur];
      for (const f of incoming) {
        if (!seen.has(f.name + f.size)) merged.push(f);
      }
      return merged;
    });
    // default the brand to the first non-.eps source file's name
    if (!brand) {
      const src = incoming.find((f) => !/\.eps$/i.test(f.name)) || incoming[0];
      if (src) setBrand(src.name.replace(/\.[^.]+$/, ""));
    }
  }

  function removeFile(i) {
    setFiles((cur) => cur.filter((_, idx) => idx !== i));
  }

  const hasSource = files.some((f) => !/\.eps$/i.test(f.name));

  return (
    <div className="space-y-5">
      <Field label="Brand name">
        <input
          className="w-full rounded-md border border-slate-300 px-3 py-2"
          placeholder="Defaults to the first file's name"
          value={brand}
          onChange={(e) => setBrand(e.target.value)}
        />
      </Field>

      <FileDrop onFiles={addFiles} />

      {files.length > 0 && (
        <ul className="space-y-1.5">
          {files.map((f, i) => (
            <li
              key={f.name + f.size}
              className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
            >
              <span className="truncate text-slate-700">
                <FileIcon name={f.name} /> {f.name}
              </span>
              <button
                onClick={() => removeFile(i)}
                className="ml-3 shrink-0 text-slate-400 hover:text-pulse-600"
                aria-label={`Remove ${f.name}`}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      <button
        disabled={!hasSource || busy}
        onClick={() => onIngest({ files, brand })}
        className="w-full rounded-md bg-pulse-500 py-2.5 font-medium text-white disabled:opacity-40"
      >
        {busy ? "Converting…" : "Upload & preview"}
      </button>
      <p className="text-xs text-slate-500">
        Add the primary <code>.ai</code> (PDF-compatible) plus any <code>.eps</code>{" "}
        masters, and extra <code>.ai</code>/<code>.pdf</code>/<code>.svg</code> files that
        hold the icon or a logo variation. Every artboard of every file is shown
        next so you can tag the Logo and the Icon. Masters pass through untouched.
      </p>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-600">{label}</span>
      {children}
    </label>
  );
}

function FileDrop({ onFiles }) {
  const [over, setOver] = useState(false);
  return (
    <label
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onFiles(e.dataTransfer.files); }}
      className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed px-4 py-8 text-center ${
        over ? "border-pulse-500 bg-pulse-50" : "border-slate-300 bg-white hover:border-pulse-500"
      }`}
    >
      <span className="text-sm font-medium text-slate-600">
        Drop files here, or click to choose <span className="text-pulse-500">*</span>
      </span>
      <span className="text-xs text-slate-400">
        .ai · .eps · .pdf · .svg — select multiple
      </span>
      <input
        type="file"
        accept=".ai,.eps,.pdf,.svg"
        multiple
        className="hidden"
        onChange={(e) => onFiles(e.target.files)}
      />
    </label>
  );
}

function FileIcon({ name }) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  const color = ext === "eps" ? "text-amber-500" : "text-pulse-500";
  return <span className={`mr-1 font-mono text-[10px] font-bold uppercase ${color}`}>{ext}</span>;
}
