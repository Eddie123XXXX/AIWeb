import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    // 部署时若静态服务期望路径为 /app/dist/build/index.html，则输出到 dist/build
    outDir: 'dist/build',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
        secure: false,
        configure: (proxy) => {
          proxy.on('proxyReq', (req) => {
            console.log('[Vite proxy]', req.method, req.path, '-> 127.0.0.1:8000');
          });
          proxy.on('error', (err, req, res) => {
            console.error('[Vite proxy error]', err.message, req.url);
          });
        },
      },
    },
  },
});
