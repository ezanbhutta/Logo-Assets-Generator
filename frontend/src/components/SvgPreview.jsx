import { useRef, useState } from "react";

// Renders the working SVG as TRUE vector and lets the CSR drag TWO boxes:
// a Logo-region box (carve the logo out of a brand-sheet/bento) and an Icon box.
//
// Coordinate mapping (§7.2): an overlay <svg> shares the artwork's exact viewBox
// and sits in the same box, so it letterboxes identically to the preview. Screen
// points are mapped to SVG user space with the browser's own getScreenCTM() —
// not hand-rolled rect math — so the box the server receives lines up with the
// artwork no matter how the preview is scaled or letterboxed. Boxes are drawn as
// <rect> in user space inside that overlay, so they align with the art natively.
export default function SvgPreview({ workingSvg, viewbox, logoBox, iconBox, active, onBox }) {
  const overlayRef = useRef(null);
  const start = useRef(null);
  const [drag, setDrag] = useState(null); // {x,y,w,h} in USER space

  const [minX, minY, maxX, maxY] = viewbox;
  const vbW = maxX - minX || 1;
  const vbH = maxY - minY || 1;
  const stroke = Math.max(vbW, vbH) / 320; // ~visible at any artboard size
  const font = Math.max(vbW, vbH) * 0.026;

  // screen px -> SVG user space, via the overlay's own CTM (accounts for the
  // viewBox AND preserveAspectRatio letterboxing exactly). Returns null until
  // the SVG is laid out.
  function toUser(clientX, clientY) {
    const svg = overlayRef.current;
    const ctm = svg && svg.getScreenCTM && svg.getScreenCTM();
    if (!ctm) return null;
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const u = pt.matrixTransform(ctm.inverse());
    return [u.x, u.y];
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
    const x = Math.min(s[0], u[0]);
    const y = Math.min(s[1], u[1]);
    const w = Math.abs(u[0] - s[0]);
    const h = Math.abs(u[1] - s[1]);
    if (w > 0.5 && h > 0.5) onBox([round(x), round(y), round(w), round(h)]);
  }

  return (
    <div className="relative w-full">
      <div
        className="svg-host relative w-full overflow-hidden rounded-lg ring-1 ring-slate-300 bg-[conic-gradient(#f8fafc_90deg,#eef2f7_0_180deg,#f8fafc_0_270deg,#eef2f7_0)] bg-[length:24px_24px]"
        style={{ aspectRatio: `${vbW} / ${vbH}` }}
        dangerouslySetInnerHTML={{ __html: workingSvg }}
      />
      <svg
        ref={overlayRef}
        viewBox={`${minX} ${minY} ${vbW} ${vbH}`}
        preserveAspectRatio="xMidYMid meet"
        className={`absolute inset-0 h-full w-full ${active ? "cursor-crosshair" : "pointer-events-none"}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        {/* full-area capture rect: SVG only hits painted geometry, so this makes
            the whole artboard interactive (pointerEvents="all" ignores fill). */}
        <rect x={minX} y={minY} width={vbW} height={vbH} fill="none" pointerEvents="all" />
        {logoBox && <BoxRect box={logoBox} color="#7229ff" label="Logo" stroke={stroke} font={font} />}
        {iconBox && <BoxRect box={iconBox} color="#10b981" label="Icon" stroke={stroke} font={font} />}
        {drag && (
          <rect
            x={drag.x}
            y={drag.y}
            width={drag.w}
            height={drag.h}
            fill={active === "icon" ? "#10b98122" : "#7229ff22"}
            stroke={active === "icon" ? "#10b981" : "#7229ff"}
            strokeWidth={stroke}
          />
        )}
      </svg>
    </div>
  );
}

function BoxRect({ box, color, label, stroke, font }) {
  const [x, y, w, h] = box;
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} fill={`${color}14`} stroke={color} strokeWidth={stroke} />
      <text x={x + stroke * 2} y={y - stroke * 2} fontSize={font} fontWeight="700" fill={color}>
        {label}
      </text>
    </g>
  );
}

const round = (v) => Math.round(v * 100) / 100;
