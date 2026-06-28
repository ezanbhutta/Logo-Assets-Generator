// Thin API client for the Logo Package Engine backend.

// Ingest one or MORE files at once. Every artboard of every file comes back so
// the CSR can tag the Logo + Icon (possibly on different artboards/files).
export async function ingest({ files, brand }) {
  const fd = new FormData();
  for (const f of files || []) fd.append("files", f);
  if (brand) fd.append("brand", brand);
  const res = await fetch("/ingest", { method: "POST", body: fd });
  if (!res.ok) {
    const detail = await safeDetail(res);
    throw new Error(detail || `Ingest failed (${res.status})`);
  }
  return res.json();
}

// Returns a Blob (the zip) on success; throws { manual, reasons } on 422.
export async function generate(body) {
  const res = await fetch("/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = await safeDetail(res);
    if (detail && detail.error === "manual_required") {
      const err = new Error("manual_required");
      err.manual = true;
      err.reasons = detail.reasons || [];
      throw err;
    }
    if (detail && detail.error === "box_miss") {
      // A drawn box covers no artwork — the job is still alive; the CSR just
      // adjusts the box and generates again. Echo the server's view of the
      // coordinates so a screenshot of this banner is a full diagnosis.
      let msg = detail.message || "A marked box doesn't cover any artwork — adjust it and try again.";
      if (detail.received && detail.artwork) {
        msg += ` [server saw ${detail.box} box ${detail.received.join(",")} vs artwork ${detail.artwork.join(",")}]`;
      }
      throw new Error(msg);
    }
    throw new Error(
      typeof detail === "string" ? detail : `Generate failed (${res.status})`
    );
  }
  return res.blob();
}

// Ask the backend to propose logo/icon boxes for an artboard (AI when a key is
// configured, geometric fallback otherwise). Returns {logo_box, icon_box, note,
// source}; never throws — returns null so the caller can fall back.
export async function segment(body) {
  try {
    const res = await fetch("/segment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function safeDetail(res) {
  try {
    const j = await res.json();
    return j.detail ?? j;
  } catch {
    return null;
  }
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
