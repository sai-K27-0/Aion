export class RealtimeAudioPlayer {
    constructor(callbacks = {}) {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.nextStartTime = 0;
        this.isPlaying = false;
        this.onStart = callbacks.onStart;
        this.onEnd = callbacks.onEnd;
        this.checkInterval = null;
    }

    async enqueue(blob) {
        if (this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
        }

        try {
            const arrayBuffer = await blob.arrayBuffer();
            const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);

            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);

            const currentTime = this.audioContext.currentTime;

            // Scheduling logic
            // If we fell behind (gap), start immediately (plus tiny buffer)
            if (this.nextStartTime < currentTime) {
                this.nextStartTime = currentTime + 0.05;
            }

            source.start(this.nextStartTime);

            // If just starting
            if (!this.isPlaying) {
                this.isPlaying = true;
                if (this.onStart) this.onStart();
                this.startMonitoring();
            }

            // Update next start time
            this.nextStartTime += audioBuffer.duration;

        } catch (err) {
            console.error("Audio Decode Error:", err);
        }
    }

    startMonitoring() {
        if (this.checkInterval) clearInterval(this.checkInterval);
        this.checkInterval = setInterval(() => {
            if (this.isPlaying && this.audioContext.currentTime >= this.nextStartTime) {
                // Playback finished
                this.isPlaying = false;
                if (this.onEnd) this.onEnd();
                clearInterval(this.checkInterval);
            }
        }, 100);
    }

    reset() {
        if (this.checkInterval) clearInterval(this.checkInterval);
        this.nextStartTime = 0;
        this.isPlaying = false;

        // Close and recreate context to stop all playing sounds immediately
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
    }
}
