import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API calls to the FastAPI backend on :8000.
const API = process.env.VITE_API_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  // Build stamp shown in the footer — lets a screenshot prove which bundle a
  // browser tab is actually running (stale-cache debugging).
  define: {
    __BUILD_STAMP__: JSON.stringify(new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC"),
  },
  server: {
    port: 5173,
    proxy: {
      "/ingest": API,
      "/generate": API,
      "/segment": API,
      "/health": API,
    },
  },
});
