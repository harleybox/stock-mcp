import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The dev server proxies /api to the FastAPI backend, so the frontend always
// calls same-origin /api/... (no CORS friction). Override with API_PORT=xxxx.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": `http://localhost:${process.env.API_PORT ?? 8000}` },
  },
});
