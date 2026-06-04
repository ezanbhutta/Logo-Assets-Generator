// HaseebMadeIt brand lockup. Placeholder mark (a "pulse" line, nodding to
// CSR-PULSE) — swap the <svg> for the real logo asset when available.
export default function Brand({ className = "" }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-navy to-[#244a60] shadow-sm ring-1 ring-black/5">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M2 13h3.5l2.2-7.5 3.8 15 2.8-9 1.8 3H22"
            stroke="#fff"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span className="text-[15px] font-semibold leading-none tracking-tight text-slate-800">
        Haseeb<span className="text-brand-red">Made</span>It
      </span>
    </div>
  );
}
