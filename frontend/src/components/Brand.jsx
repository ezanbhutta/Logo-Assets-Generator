// HaseebMadeIt / CSR-Pulse brand lockup: the purple tile + white grid mark.
export function PulseMark({ size = 36 }) {
  return (
    <span
      className="grid place-items-center rounded-xl bg-pulse-500 shadow-sm ring-1 ring-black/5"
      style={{ width: size, height: size }}
    >
      <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 64 64" fill="#fff" aria-hidden="true">
        <rect x="27" y="6" width="10" height="22" rx="5" transform="rotate(-9 32 17)" />
        <rect x="27" y="36" width="10" height="22" rx="5" transform="rotate(-9 32 47)" />
        <rect x="9" y="13" width="10" height="17" rx="5" transform="rotate(-9 14 21)" />
        <rect x="45" y="13" width="10" height="17" rx="5" transform="rotate(-9 50 21)" />
        <rect x="9" y="34" width="10" height="17" rx="5" transform="rotate(-9 14 42)" />
        <rect x="45" y="34" width="10" height="17" rx="5" transform="rotate(-9 50 42)" />
      </svg>
    </span>
  );
}

export default function Brand({ className = "" }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <PulseMark size={34} />
      <span className="text-[15px] font-bold leading-none tracking-tight text-ink">
        Haseeb<span className="text-pulse-500">Made</span>It
      </span>
    </div>
  );
}
