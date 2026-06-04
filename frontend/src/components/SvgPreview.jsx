import { useRef, useState, useCallback } from "react";

// Renders the working SVG as TRUE vector (injected DOM, not a raster) and lets
// the CSR drag one box to mark the icon. The pixel box is converted to SVG
// user-space before it leaves the component (§7.2 / §8 rule 1).
export default function SvgPreview({ workingSvg, viewbox, box, onBox, enabled }) {
  const hostRef = useRef(null);
  const [drag, setDrag] = useState(null); // {l,t,w,h} in host pixels

  const [minX, minY, maxX, maxY] = viewbox;
  const vbW = maxX - minX;
  const vbH = maxY - minY;

  const toUserSpace = useCallback(
    (px, py) => {
      const r = hostRef.current.getBoundingClientRect();
      const sx = vbW / r.width;
      const sy = vbH / r.height;
      return [(px - r.left) * sx + minX, (py - r.top) * sy + minY];
    },
    [vbW, vbH, minX, minY]
  );

  const start = useRef(null);

  function onPointerDown(e) {
    if (!enabled) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    start.current = { x: e.clientX, y: e.clientY };
    setDrag({ l: localX(e), t: localY(e), w: 0, h: 0 });
  }
  function onPointerMove(e) {
    if (!enabled || !start.current) return;
    const x0 = start.current.x;
    const y0 = start.current.y;
    const r = hostRef.current.getBoundingClientRect();
    const l = Math.min(x0, e.clientX) - r.left;
    const t = Math.min(y0, e.clientY) - r.top;
    setDrag({ l, t, w: Math.abs(e.clientX - x0), h: Math.abs(e.clientY - y0) });
  }
  function onPointerUp(e) {
    if (!enabled || !start.current) return;
    const [ux0, uy0] = toUserSpace(start.current.x, start.current.y);
    const [ux1, uy1] = toUserSpace(e.clientX, e.clientY);
    start.current = null;
    const x = Math.min(ux0, ux1);
    const y = Math.min(uy0, uy1);
    const w = Math.abs(ux1 - ux0);
    const h = Math.abs(uy1 - uy0);
    if (w > 0.5 && h > 0.5) onBox([round(x), round(y), round(w), round(h)]);
  }

  function localX(e) {
    return e.clientX - hostRef.current.getBoundingClientRect().left;
  }
  function localY(e) {
    return e.clientY - hostRef.current.getBoundingClientRect().top;
  }

  return (
    <div className="relative w-full">
      <div
        ref={hostRef}
        className="svg-host relative w-full overflow-hidden rounded-lg border border-slate-300 bg-[conic-gradient(#f8fafc_90deg,#eef2f7_0_180deg,#f8fafc_0_270deg,#eef2f7_0)] bg-[length:24px_24px]"
        style={{ aspectRatio: `${vbW} / ${vbH}` }}
        dangerouslySetInnerHTML={{ __html: workingSvg }}
      />
      {/* Drag overlay — captures pointer events when selecting */}
      <div
        className={`absolute inset-0 ${enabled ? "cursor-crosshair" : "pointer-events-none"}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        {drag && (
          <div
            className="absolute border-2 border-pulse-500 bg-pulse-500/10"
            style={{ left: drag.l, top: drag.t, width: drag.w, height: drag.h }}
          />
        )}
      </div>
      {box && (
        <div className="mt-2 text-xs text-slate-500">
          Icon box (user space): x {box[0]}, y {box[1]}, w {box[2]}, h {box[3]}
        </div>
      )}
    </div>
  );
}

const round = (v) => Math.round(v * 100) / 100;
