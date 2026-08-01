import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5050', // 5000 collides with macOS AirPlay Receiver — see backend/start_backend.py
        changeOrigin: true,
        secure: false,
        ws: true, // proxy the telemetry WebSocket too
        timeout: 30000, // Increase timeout for backend startup
      },
      '/ws': {
        target: 'http://127.0.0.1:5050', // 5000 collides with macOS AirPlay Receiver — see backend/start_backend.py
        changeOrigin: true,
        secure: false,
        ws: true, // Control tab's /ws/control-telemetry stream (core/control/session.py)
        timeout: 30000,
      }
    },
    // Add a small delay to allow backend to start

    middlewareMode: false,
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets'
  }
})