import Brand from "./Brand.jsx";

export default function TopBar({ onNew, showNew }) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3">
          <Brand />
          <span className="hidden h-5 w-px bg-slate-200 sm:block" />
          <span className="hidden text-sm font-medium text-slate-500 sm:block">
            Logo Package Engine
          </span>
        </div>
        {showNew && (
          <button
            onClick={onNew}
            className="inline-flex items-center gap-1.5 rounded-lg bg-pulse-500 px-3.5 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-pulse-600"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
              <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
            </svg>
            New logo
          </button>
        )}
      </div>
    </header>
  );
}
