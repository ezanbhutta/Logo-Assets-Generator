// HaseebMadeIt / CSR-Pulse brand lockup: the purple tile + white grid mark.
export function PulseMark({ size = 36 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true"
         className="shrink-0 rounded-[22%] shadow-sm ring-1 ring-black/5">
      <rect width="100" height="100" rx="24" fill="#7229ff" />
      <g fill="#fff" transform="rotate(-9 50 50)">
        <rect x="45.4" y="27" width="9.2" height="24" rx="4.6" />
        <rect x="45.4" y="53" width="9.2" height="24" rx="4.6" />
        <rect x="32.5" y="33" width="9.2" height="19" rx="4.6" />
        <rect x="58.3" y="33" width="9.2" height="14" rx="4.6" />
        <rect x="32.5" y="54" width="9.2" height="14" rx="4.6" />
        <rect x="58.3" y="49" width="9.2" height="23" rx="4.6" />
      </g>
    </svg>
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
