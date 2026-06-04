// Lightweight progress indicator across the CSR flow.
const STEPS = ["Upload", "Artboard", "Configure", "Download"];

export default function Steps({ current }) {
  return (
    <ol className="mx-auto mb-7 flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-2 px-4 text-xs">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const state = n < current ? "done" : n === current ? "active" : "todo";
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              className={`grid h-6 w-6 place-items-center rounded-full text-[11px] font-bold transition ${
                state === "done"
                  ? "bg-emerald-500 text-white"
                  : state === "active"
                  ? "bg-brand-navy text-white ring-4 ring-brand-navy/10"
                  : "bg-slate-200 text-slate-500"
              }`}
            >
              {state === "done" ? "✓" : n}
            </span>
            <span className={state === "todo" ? "text-slate-400" : "font-medium text-slate-700"}>
              {label}
            </span>
            {i < STEPS.length - 1 && <span className="h-px w-6 bg-slate-200 sm:w-10" />}
          </li>
        );
      })}
    </ol>
  );
}
