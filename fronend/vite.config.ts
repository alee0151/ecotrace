import { defineConfig } from 'vite'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

function figmaAssetResolver() {
  return {
    name: 'figma-asset-resolver',
    resolveId(id: string) {
      if (id.startsWith('figma:asset/')) {
        const filename = id.replace('figma:asset/', '')
        return path.resolve(__dirname, 'src/assets', filename)
      }
    },
  }
}

export default defineConfig({
  plugins: [
    figmaAssetResolver(),
    // The React and Tailwind plugins are both required for Make, even if
    // Tailwind is not being actively used – do not remove them
    react(),
    tailwindcss(),
  ],

  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(__dirname, './src'),
    },
  },

  // ─── Dev-server proxy ────────────────────────────────────────────────────
  // During development, requests to /api/* (and /health) are forwarded to
  // the FastAPI backend running on port 8000. This avoids CORS issues and
  // removes the need for a hard-coded host in component code.
  //
  // Usage:
  //   1. Start the backend:  cd backend && uvicorn main:app --reload
  //   2. Start the frontend: cd fronend && pnpm dev
  //   3. The frontend fetches /api/search — Vite proxies it to
  //      http://127.0.0.1:8000/api/search transparently.
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // Do NOT rewrite the path — the backend already has /api/* routes.
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },

  // File types to support raw imports. Never add .css, .tsx, or .ts files to this.
  assetsInclude: ['**/*.svg', '**/*.csv'],
})
