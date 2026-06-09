import { useRef, useState, useCallback } from "react";

// Renders the working SVG as TRUE vector and lets the CSR drag TWO boxes:
// a Logo-region box (carve the logo out of a brand-sheet/bento) and an Icon box.
// Both are converted to SVG user space before leaving the component (§7.2).
export default function SvgPreview({ workingSvg, viewbox, logoBox, iconBox, active, onBox }) {
  const hostRef = useRef(null);
  const [drag, setDrag] = useState(null); // {l,t,w,h} in host pixels
  const start = useRef(null);

  const [minX, minY, maxX, maxY] = viewbox;
  // Guard a degenerate viewBox (w or h == 0) so the aspect ratio and the
  // pixel→user-space math never divide by zero.
  const vbW = maxX - minX || 1;
  const vbH = maxY - minY || 1;

  const toUserSpace = useCallback(
    (px, py) => {
      const r = hostRef.current.getBoundingClientRect();
      return [(px - r.left) * (vbW / r.width) + minX, (py - r.top) * (vbH / r.height) + minY];
    },
    [vbW, vbH, minX, minY]
  );

  function onPointerDown(e) {
    if (!active) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    start.current = { x: e.clientX, y: e.clientY };
    const r = hostRef.current.getBoundingClientRect();
    setDrag({ l: e.clientX - r.left, t: e.clientY - r.top, w: 0, h: 0 });
  }
  function onPointerMove(e) {
    if (!active || !start.current) return;
    const r = hostRef.current.getBoundingClientRect();
    const x0 = start.current.x, y0 = start.current.y;
    setDrag({
      l: Math.min(x0, e.clientX) - r.left,
      t: Math.min(y0, e.clientY) - r.top,
      w: Math.abs(e.clientX - x0),
      h: Math.abs(e.clientY - y0),
    });
  }
  function onPointerUp(e) {
    if (!active || !start.current) return;
    const [ux0, uy0] = toUserSpace(start.current.x, start.current.y);
    const [ux1, uy1] = toUserSpace(e.clientX, e.clientY);
    start.current = null;
    setDrag(null);
    const w = Math.abs(ux1 - ux0), h = Math.abs(uy1 - uy0);
    if (w > 0.5 && h > 0.5) {
      onBox([round(Math.min(ux0, ux1)), round(Math.min(uy0, uy1)), round(w), round(h)]);
    }
  }

  // user-space box -> percentage rect of the host (resolution-independent)
  const pct = (box) =>
    box && {
      left: `${((box[0] - minX) / vbW) * 100}%`,
      top: `${((box[1] - minY) / vbH) * 100}%`,
      width: `${(box[2] / vbW) * 100}%`,
      height: `${(box[3] / vbH) * 100}%`,
    };

  return (
    <div className="relative w-full">
      <div
        ref={hostRef}
        className="svg-host relative w-full overflow-hidden rounded-lg border border-slate-300 bg-[conic-gradient(#f8fafc_90deg,#eef2f7_0_180deg,#f8fafc_0_270deg,#eef2f7_0)] bg-[length:24px_24px]"
        style={{ aspectRatio: `${vbW} / ${vbH}` }}
        dangerouslySetInnerHTML={{ __html: workingSvg }}
      />
      <div
        className={`absolute inset-0 ${active ? "cursor-crosshair" : "pointer-events-none"}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        {logoBox && <BoxRect style={pct(logoBox)} color="pulse" label="Logo" />}
        {iconBox && <BoxRect style={pct(iconBox)} color="emerald" label="Icon" />}
        {drag && (
          <div
            className={`absolute border-2 ${
              active === "icon" ? "border-emerald-500 bg-emerald-500/10" : "border-pulse-500 bg-pulse-500/10"
            }`}
            style={{ left: drag.l, top: drag.t, width: drag.w, height: drag.h }}
          />
        )}
      </div>
    </div>
  );
}

function BoxRect({ style, color, label }) {
  const c =
    color === "emerald"
      ? "border-emerald-500 bg-emerald-500/5 text-emerald-700"
      : "border-pulse-500 bg-pulse-500/5 text-pulse-700";
  return (
    <div className={`absolute border-2 ${c}`} style={style}>
      <span className={`absolute -top-5 left-0 rounded px-1 text-[10px] font-semibold ${c} bg-white/90`}>
        {label}
      </span>
    </div>
  );
}

const round = (v) => Math.round(v * 100) / 100;
