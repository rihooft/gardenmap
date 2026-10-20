import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// base './' : l'interface est servie sous un chemin d'ingress variable (/api/hassio_ingress/<jeton>/)
export default defineConfig({
  base: './',
  plugins: [svelte()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8099' },
  },
  build: { chunkSizeWarningLimit: 800 },
});
