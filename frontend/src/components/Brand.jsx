// HaseebMadeIt / CSR-Pulse brand lockup: the exact logo asset (public/favicon.svg).
export function PulseMark({ size = 34 }) {
  return (
    <img
      src="/favicon.svg"
      width={size}
      height={size}
      alt="HaseebMadeIt"
      className="shrink-0"
      style={{ width: size, height: size }}
    />
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
