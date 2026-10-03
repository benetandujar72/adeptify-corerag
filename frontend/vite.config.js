var _a;
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        host: '127.0.0.1',
        proxy: {
            '/api': {
                target: ((_a = process.env.VITE_API_BASE_URL) === null || _a === void 0 ? void 0 : _a.replace('/api', '')) || 'http://localhost:8000',
                changeOrigin: true,
            },
        },
    },
    preview: {
        port: 5173,
        host: '127.0.0.1',
    },
});
