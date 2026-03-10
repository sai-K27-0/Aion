import { invoke } from '@tauri-apps/api/core';

class ScreenCaptureService {
    /**
     * Capture the primary screen via Rust backend.
     * Returns base64 encoded PNG string.
     */
    async captureScreen() {
        try {
            const base64Image = await invoke('capture_screen');
            return base64Image;
        } catch (error) {
            console.error('Failed to capture screen:', error);
            throw error;
        }
    }

    /**
     * Send captured image to AI backend for analysis.
     */
    async analyzeScreen(base64Image) {
        // Convert base64 to blob
        const byteCharacters = atob(base64Image);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: 'image/png' });

        // Create FormData
        const formData = new FormData();
        formData.append('file', blob, 'screenshot.png');
        formData.append('extract_text', 'true');

        // Send to Python Backend (use user-configured server URL)
        const apiBase = localStorage.getItem('aion_server_url') || 'http://localhost:8000/api/v1';
        const response = await fetch(`${apiBase}/ai/screen/analyze`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Analysis failed: ${response.statusText} - ${errorText}`);
        }

        return await response.json();
    }
}

export const screenCaptureService = new ScreenCaptureService();
