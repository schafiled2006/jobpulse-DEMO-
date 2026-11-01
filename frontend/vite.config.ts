// Vite config for the JobPulse frontend.
//
// The dev server runs on port 3000 because that is the origin the backend's
// CORS settings allow by default (`CORS_ORIGINS=["http://localhost:3000"]`).
// API calls go to http://127.0.0.1:8000 directly (see src/api.ts); only the
// browser's origin must match the backend's allow-list.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
  },
});
