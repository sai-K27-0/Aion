import { defineConfig } from 'vite';

export default defineConfig({
    // Prevent vite from obscuring Rust errors
    clearScreen: false,

    // Tauri expects a fixed port
    server: {
        port: 1420,
        strictPort: true,
    },

    // Configure env prefix for Tauri
    envPrefix: ['VITE_', 'TAURI_'],

    build: {
        // Tauri supports es2021
        target: process.env.TAURI_PLATFORM === 'windows' ? 'chrome105' : 'safari13',
        // Don't minify for debug builds
        minify: !process.env.TAURI_DEBUG ? 'esbuild' : false,
        // Produce sourcemaps for debug builds
        sourcemap: !!process.env.TAURI_DEBUG,
    },
});
