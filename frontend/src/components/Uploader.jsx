import { useState } from "react";

// Step 1: Brand name (defaults to the .ai filename) + .ai/.eps upload (§3.1-3.3).
export default function Uploader({ onIngest, busy }) {
  const [ai, setAi] = useState(null);
  const [eps, setEps] = useState(null);
  const [brand, setBrand] = useState("");

  function pickAi(f) {
    setAi(f);
    if (f && !brand) setBrand(f.name.replace(/\.[^.]+$/, ""));
  }

  return (
    <div className="space-y-5">
      <Field label="Brand name">
        <input
          className="w-full rounded-md border border-slate-300 px-3 py-2"
          placeholder="Defaults to the .ai filename"
          value={brand}
          onChange={(e) => setBrand(e.target.value)}
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <FileDrop label="Primary logo (.ai)" accept=".ai,.pdf,.svg" file={ai} onFile={pickAi} required />
        <FileDrop label="Editable master (.eps)" accept=".eps" file={eps} onFile={setEps} />
      </div>

      <button
        disabled={!ai || busy}
        onClick={() => onIngest({ ai, eps, brand })}
        className="w-full rounded-md bg-pulse-500 py-2.5 font-medium text-white disabled:opacity-40"
      >
        {busy ? "Converting…" : "Upload & preview"}
      </button>
      <p className="text-xs text-slate-500">
        The <code>.ai</code> must be PDF-compatible (Illustrator "Create PDF
        Compatible File"). Both files pass through to the package untouched.
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

function FileDrop({ label, accept, file, onFile, required }) {
  return (
    <label className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-slate-300 bg-white px-4 py-6 text-center hover:border-pulse-500">
      <span className="text-sm font-medium text-slate-600">
        {label} {required && <span className="text-pulse-500">*</span>}
      </span>
      <span className="text-xs text-slate-400">{file ? file.name : "Click to choose"}</span>
      <input
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onFile(e.target.files?.[0] || null)}
      />
    </label>
  );
}
