import { useRef, useState, useEffect } from "react";

// Renders the working SVG as TRUE vector and lets the CSR drag TWO boxes:
// a Logo-region box (carve the logo out of a brand-sheet/bento) and an Icon box.
//
// Coordinate mapping (§7.2): screen <-> SVG user space goes through the ACTUAL
// injected artwork SVG's own getScreenCTM() — the browser's ground-truth
// transform for what it rendered. This matches whatever viewBox/scale the
// server's converter produced (poppler emits pt on one host, px on another) and
// the geometry the server measured from that same SVG, so a box drawn on the
// mark lands on it server-side. Never hand-rolled rect math, and never a
// separate viewBox guess — those silently mis-mapped when the converter's scale
// differed from the `viewbox` prop.
export default function SvgPreview({ workingSvg, viewbox, logoBox, iconBox, active, onBox }) {
  const hostRef = useRef(null);
  const start = useRef(null);
  const [drag, setDrag] = useState(null); // {x,y,w,h} in USER space
  const [, setTick] = useState(0); // bump to reposition overlays on layout change

  // Reposition overlay boxes whenever the SVG is (re)injected or the host
  // resizes — getScreenCTM depends on the live layout.
  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setTick((t) => t + 1));
    ro.observe(el);
    const id = requestAnimationFrame(() => setTick((t) => t + 1));
    return () => {
      ro.disconnect();
      cancelAnimationFrame(id);
    };
  }, [workingSvg]);

  const svgEl = () => hostRef.current && hostRef.current.querySelector("svg");

  // screen px -> SVG user space, via the artwork SVG's own CTM.
  function toUser(clientX, clientY) {
    const svg = svgEl();
    const m = svg && svg.getScreenCTM && svg.getScreenCTM();
    if (!m) return null;
    const p = svg.createSVGPoint();
    p.x = clientX;
    p.y = clientY;
    const u = p.matrixTransform(m.inverse());
    return [u.x, u.y];
  }

  // SVG user space -> host-relative CSS px, to position overlay boxes exactly
  // over the artwork (same CTM, so letterboxing/scale are handled for free).
  function toHostPx(ux, uy) {
    const svg = svgEl();
    const host = hostRef.current;
    const m = svg && svg.getScreenCTM && svg.getScreenCTM();
    if (!m || !host) return null;
    const p = svg.createSVGPoint();
    p.x = ux;
    p.y = uy;
    const s = p.matrixTransform(m);
    const r = host.getBoundingClientRect();
    return [s.x - r.left, s.y - r.top];
  }

  function boxStyle(b) {
    if (!b) return null;
    const a = toHostPx(b[0], b[1]);
    const c = toHostPx(b[0] + b[2], b[1] + b[3]);
    if (!a || !c) return null;
    return {
      left: Math.min(a[0], c[0]),
      top: Math.min(a[1], c[1]),
      width: Math.abs(c[0] - a[0]),
      height: Math.abs(c[1] - a[1]),
    };
  }

  function onPointerDown(e) {
    if (!active) return;
    const u = toUser(e.clientX, e.clientY);
    if (!u) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    start.current = u;
    setDrag({ x: u[0], y: u[1], w: 0, h: 0 });
  }
  function onPointerMove(e) {
    if (!active || !start.current) return;
    const u = toUser(e.clientX, e.clientY);
    if (!u) return;
    setDrag({
      x: Math.min(start.current[0], u[0]),
      y: Math.min(start.current[1], u[1]),
      w: Math.abs(u[0] - start.current[0]),
      h: Math.abs(u[1] - start.current[1]),
    });
  }
  function onPointerUp(e) {
    if (!active || !start.current) return;
    const u = toUser(e.clientX, e.clientY);
    const s = start.current;
    start.current = null;
    setDrag(null);
    if (!u) return;
    const w = Math.abs(u[0] - s[0]);
    const h = Math.abs(u[1] - s[1]);
    if (w > 0.5 && h > 0.5) {
      onBox([round(Math.min(s[0], u[0])), round(Math.min(s[1], u[1])), round(w), round(h)]);
    }
  }

  // Host aspect ratio (cosmetic — keeps the preview from letterboxing). Mapping
  // does NOT depend on this; it uses the live CTM.
  const [minX, minY, maxX, maxY] = viewbox;
  const arW = maxX - minX || 1;
  const arH = maxY - minY || 1;

  const logoStyle = logoBox && boxStyle(logoBox);
  const iconStyle = iconBox && boxStyle(iconBox);
  const dragStyle = drag && boxStyle([drag.x, drag.y, drag.w, drag.h]);

  return (
    <div className="relative w-full">
      <div
        ref={hostRef}
        className="svg-host relative w-full overflow-hidden rounded-lg ring-1 ring-slate-300 bg-[conic-gradient(#f8fafc_90deg,#eef2f7_0_180deg,#f8fafc_0_270deg,#eef2f7_0)] bg-[length:24px_24px]"
        style={{ aspectRatio: `${arW} / ${arH}` }}
        dangerouslySetInnerHTML={{ __html: workingSvg }}
      />
      <div
        className={`absolute inset-0 ${active ? "cursor-crosshair" : "pointer-events-none"}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        {logoStyle && <BoxRect style={logoStyle} color="pulse" label="Logo" />}
        {iconStyle && <BoxRect style={iconStyle} color="emerald" label="Icon" />}
        {dragStyle && (
          <div
            className={`absolute border-2 ${
              active === "icon" ? "border-emerald-500 bg-emerald-500/10" : "border-pulse-500 bg-pulse-500/10"
            }`}
            style={dragStyle}
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
