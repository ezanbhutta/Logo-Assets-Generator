// Thin API client for the Logo Package Engine backend.

export async function ingest({ ai, eps, brand }) {
  const fd = new FormData();
  fd.append("ai", ai);
  if (eps) fd.append("eps", eps);
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
