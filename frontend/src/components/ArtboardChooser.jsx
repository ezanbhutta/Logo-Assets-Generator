// Shown when the uploaded .ai has multiple artboards: the CSR must clarify
// which artboard is the primary logo before any files are generated.
export default function ArtboardChooser({ artboards, primaryIndex, onPick }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-1 flex items-center gap-2">
        <span className="grid h-6 w-6 place-items-center rounded-full bg-pulse-500 text-xs font-bold text-white">
          ?
        </span>
        <h2 className="text-base font-semibold text-slate-700">
          This file has {artboards.length} artboards — which is the primary logo?
        </h2>
      </div>
      <p className="mb-4 text-sm text-slate-500">
        The whole package is generated from the artboard you pick. We suggest the
        most complete lockup.
      </p>

      <div className="grid gap-4 sm:grid-cols-3">
        {artboards.map((b) => {
          const [minX, minY, maxX, maxY] = b.viewbox;
          const w = Math.max(maxX - minX, 1);
          const h = Math.max(maxY - minY, 1);
          const suggested = b.index === primaryIndex;
          const manual = b.classification === "manual";
          return (
            <button
              key={b.index}
              onClick={() => onPick(b.index)}
              className={`group rounded-lg border-2 p-2 text-left transition ${
                suggested ? "border-pulse-500" : "border-slate-200 hover:border-slate-400"
              }`}
            >
              <div
                className="svg-host w-full overflow-hidden rounded bg-[conic-gradient(#f8fafc_90deg,#eef2f7_0_180deg,#f8fafc_0_270deg,#eef2f7_0)] bg-[length:18px_18px]"
                style={{ aspectRatio: `${w} / ${h}` }}
                dangerouslySetInnerHTML={{ __html: b.working_svg }}
              />
              <div className="mt-2 flex items-center justify-between">
                <span className="text-sm font-medium text-slate-700">{b.label}</span>
                <div className="flex gap-1">
                  {suggested && (
                    <span className="rounded bg-pulse-500 px-1.5 py-0.5 text-[10px] text-white">
                      suggested
                    </span>
                  )}
                  {manual && (
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700">
                      manual
                    </span>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
