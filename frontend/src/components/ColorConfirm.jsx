// Step 2b: confirm detected brand colors / gradient; remove a stray before it
// propagates into 50+ files (§3.5).
export default function ColorConfirm({ result, removed, onToggle }) {
  const solids = result.swatches.filter((s) => s.type === "solid");
  const grads = result.swatches.filter((s) => s.type === "gradient");

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-slate-600">Detected colors</h3>

      <div className="flex flex-wrap gap-2">
        {solids.map((s) => {
          const isRemoved = removed.includes(s.value);
          return (
            <button
              key={s.value}
              onClick={() => onToggle(s.value)}
              title={isRemoved ? "Removed — click to keep" : "Click to remove as a stray"}
              className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${
                isRemoved ? "border-slate-200 opacity-40" : "border-slate-300"
              }`}
            >
              <span
                className="h-5 w-5 rounded border border-slate-300"
                style={{ background: s.value, textDecoration: isRemoved ? "line-through" : "none" }}
              />
              <span className={isRemoved ? "line-through" : ""}>{s.value}</span>
              {s.brand && !isRemoved && (
                <span className="rounded bg-slate-100 px-1 text-[10px] uppercase text-slate-500">brand</span>
              )}
            </button>
          );
        })}

        {grads.map((g) => (
          <span
            key={g.value}
            className="flex items-center gap-2 rounded-md border border-slate-300 px-2.5 py-1.5 text-xs"
          >
            <span className="h-5 w-5 rounded border border-slate-300 bg-gradient-to-br from-amber-400 via-orange-500 to-brand-red" />
            gradient
          </span>
        ))}
      </div>

      <div className="flex gap-4 text-xs text-slate-500">
        <Badge label="brand-A (dark)" color={result.brand_a} />
        <Badge label="brand-B (vivid)" color={result.brand_b} />
        <span>{result.is_gradient ? "Gradient logo" : "Solid logo"}</span>
      </div>
    </div>
  );
}

function Badge({ label, color }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-4 w-4 rounded border border-slate-300" style={{ background: color }} />
      {label} {color}
    </span>
  );
}
