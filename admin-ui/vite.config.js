import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  define: {
    // The app was migrated from CRA and still reads process.env.* at runtime;
    // Vite does not shim `process`, so these must be statically replaced.
    'process.env.REACT_APP_API_URL': JSON.stringify(process.env.REACT_APP_API_URL || ''),
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'development'),
  },
  server: {
    port: 3000,
    host: true, // Needed for docker port mapping
    strictPort: true,
  },
  build: {
    outDir: 'build',
  }
});
