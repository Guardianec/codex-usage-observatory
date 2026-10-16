import {defineConfig} from 'vite';
export default defineConfig({
  root: 'frontend',
  build: {outDir: 'dist', emptyOutDir: true},
  server: {proxy: {'/api': {target:'http://127.0.0.1:8765',changeOrigin:true,
    configure(proxy){proxy.on('proxyReq',req=>req.setHeader('origin','http://127.0.0.1:8765'));}}}}
});
