import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/import-file': 'http://localhost:8000',
      '/import-url': 'http://localhost:8000',
      '/video': 'http://localhost:8000',
      '/thumbnail': 'http://localhost:8000',
      '/transcribe': 'http://localhost:8000',
      '/transcribe-status': 'http://localhost:8000',
      '/highlights': 'http://localhost:8000',
      '/export': 'http://localhost:8000',
      '/exports': 'http://localhost:8000',
      '/metadata': 'http://localhost:8000',
      '/thumbnails': 'http://localhost:8000',
      '/diagnostics': 'http://localhost:8000',
      '/test-report': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
});
