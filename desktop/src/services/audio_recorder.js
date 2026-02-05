export class AudioRecorder {
    constructor(callbacks = {}) {
        this.mediaRecorder = null;
        this.stream = null;
        this.onDataAvailable = callbacks.onDataAvailable;
        this.onStart = callbacks.onStart;
        this.onStop = callbacks.onStop;
        this.onError = callbacks.onError;
    }

    async start() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            // Check for supported mime types
            let mimeType = 'audio/webm'; // Default for Chrome/Edge
            if (!MediaRecorder.isTypeSupported(mimeType)) {
                if (MediaRecorder.isTypeSupported('audio/mp4')) mimeType = 'audio/mp4';
                else if (MediaRecorder.isTypeSupported('audio/ogg')) mimeType = 'audio/ogg';
            }

            this.mediaRecorder = new MediaRecorder(this.stream, { mimeType });

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0 && this.onDataAvailable) {
                    this.onDataAvailable(event.data);
                }
            };

            this.mediaRecorder.onstart = () => {
                if (this.onStart) this.onStart();
            };

            this.mediaRecorder.onstop = () => {
                if (this.onStop) this.onStop();
            };

            // Collect chunks every 100ms
            this.mediaRecorder.start(100);

        } catch (err) {
            console.error("Microphone access failed:", err);
            if (this.onError) this.onError(err);
        }
    }

    stop() {
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        this.mediaRecorder = null;
    }
}
