import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Served from https://<user>.github.io/inflation-and-monetary-policy/ —
  // a project Pages site, not a user/org root site, so every asset URL needs
  // this prefix or they'll 404 under the repo subpath.
  base: '/inflation-and-monetary-policy/',
  build: { outDir: 'dist', sourcemap: false },
})
