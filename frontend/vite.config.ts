import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://backend:8000",
      "/ws": {
        target: "ws://backend:8000",
        ws: true,
      },
    },
  },
});
