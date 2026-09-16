import react from "@vitejs/plugin-react";
import { resolve } from "path";
import { defineConfig } from "vite";

// Library build: one ES module that runs against the Console's own React and
// antd (`window.QwenPaw.host`), so nothing from React is bundled.
export default defineConfig({
  plugins: [react({ jsxRuntime: "classic" })],
  build: {
    lib: {
      entry: resolve(__dirname, "src/index.tsx"),
      formats: ["es"],
      fileName: () => "index.js",
    },
    outDir: resolve(__dirname, "dist"),
    emptyOutDir: true,
    rollupOptions: { external: ["react", "react-dom"] },
  },
});
