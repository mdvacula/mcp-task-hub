import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// Served by the hub at /ui/ — assets must resolve relative to that base.
export default defineConfig({
  base: "/ui/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // dev-only: talk to a locally running hub
      "/tasks": "http://127.0.0.1:8050",
      "/health": "http://127.0.0.1:8050",
    },
  },
})
