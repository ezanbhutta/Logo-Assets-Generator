// Shown after ingest: every artboard of every uploaded file, grouped by file.
// The CSR tags ONE as the Logo lockup and (optionally) ONE as the Icon source —
// they may be on different artboards or even different files. The package is
// then generated from exactly those two tagged artboards.
export default function ArtboardTagger({
  artboards,
  files,
  primaryIndex,
  logoArtboard,
  iconArtboard,
  onTag,
  onContinue,
}) {
  // group artboards by their source file (preserve file + page order)
  const groups = [];
  for (const b of artboards) {
    let g = groups.find((x) => x.fi === b.file_index);
    if (!g) {
      g = { fi: b.file_index, name: b.file_name || files?.[b.file_index] || "File", boards: [] };
      groups.push(g);
    }
    g.boards.push(b);
  }
  const multiFile = groups.length > 1;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-1 flex items-center gap-2">
        <span className="grid h-6 w-6 place-items-center rounded-full bg-pulse-500 text-xs font-bold text-white">
          2
        </span>
        <h2 className="text-base font-semibold text-slate-700">
          Tag the Logo and the Icon
        </h2>
      </div>
      <p className="mb-5 text-sm text-slate-500">
        {artboards.length} artboard{artboards.length === 1 ? "" : "s"}
        {multiFile ? ` across ${groups.length} files` : ""}. Mark which one is the{" "}
        <Tag tone="logo">Logo</Tag> lockup and (optionally) which is the{" "}
        <Tag tone="icon">Icon</Tag>. The icon can be a separate artboard, the same
        one, or left untagged for a logo-only package.
      </p>

      <div className="space-y-6">
        {groups.map((g) => (
          <div key={g.fi}>
            {multiFile && (
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                {g.name}
              </div>
            )}
            <div className="grid gap-4 sm:grid-cols-3">
              {g.boards.map((b) => (
                <BoardCard
                  key={b.index}
                  board={b}
                  suggested={b.index === primaryIndex}
                  isLogo={b.index === logoArtboard}
                  isIcon={b.index === iconArtboard}
                  onTag={onTag}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 flex items-center justify-between">
        <p className="text-xs text-slate-500">
          {logoArtboard == null
            ? "Tag a Logo artboard to continue."
            : iconArtboard == null
            ? "No Icon tagged — the package will be logo-only (you can still mark an icon inside the logo next)."
            : iconArtboard === logoArtboard
            ? "Icon shares the logo artboard — mark its region next."
            : "Logo and Icon tagged on separate artboards."}
        </p>
        <button
          disabled={logoArtboard == null}
          onClick={onContinue}
          className="rounded-md bg-pulse-500 px-5 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          Continue →
        </button>
      </div>
    </div>
  );
}

function BoardCard({ board: b, suggested, isLogo, isIcon, onTag }) {
  const [minX, minY, maxX, maxY] = b.viewbox;
  const w = Math.max(maxX - minX, 1);
  const h = Math.max(maxY - minY, 1);
  const manual = b.classification === "manual";
  const ring = isLogo
    ? "border-pulse-500 ring-2 ring-pulse-200"
    : isIcon
    ? "border-emerald-500 ring-2 ring-emerald-200"
    : "border-slate-200";
  return (
    <div className={`rounded-lg border-2 p-2 transition ${ring}`}>
      <div
        className="svg-host w-full overflow-hidden rounded bg-[conic-gradient(#f8fafc_90deg,#eef2f7_0_180deg,#f8fafc_0_270deg,#eef2f7_0)] bg-[length:18px_18px]"
        style={{ aspectRatio: `${w} / ${h}` }}
        dangerouslySetInnerHTML={{ __html: b.working_svg }}
      />
      <div className="mt-2 flex items-center justify-between gap-1">
        <span className="truncate text-sm font-medium text-slate-700">{b.label}</span>
        <div className="flex shrink-0 gap-1">
          {suggested && (
            <span className="rounded bg-pulse-100 px-1.5 py-0.5 text-[10px] text-pulse-700">
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
      <div className="mt-2 grid grid-cols-2 gap-1.5">
        <RoleButton active={isLogo} tone="logo" onClick={() => onTag("logo", b.index)}>
          Logo
        </RoleButton>
        <RoleButton active={isIcon} tone="icon" onClick={() => onTag("icon", b.index)}>
          Icon
        </RoleButton>
      </div>
    </div>
  );
}

function RoleButton({ active, tone, onClick, children }) {
  const on =
    tone === "logo" ? "bg-pulse-500 text-white" : "bg-emerald-500 text-white";
  const off = "bg-slate-100 text-slate-600 hover:bg-slate-200";
  const dot = tone === "logo"
    ? active ? "bg-pulse-200" : "bg-pulse-400"
    : active ? "bg-emerald-200" : "bg-emerald-400";
  return (
    <button
      onClick={onClick}
      className={`flex items-center justify-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium ${
        active ? on : off
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {children}
    </button>
  );
}

function Tag({ tone, children }) {
  const c = tone === "logo" ? "bg-pulse-100 text-pulse-700" : "bg-emerald-100 text-emerald-700";
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${c}`}>{children}</span>;
}
