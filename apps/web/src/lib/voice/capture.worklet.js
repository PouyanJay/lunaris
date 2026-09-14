/* global AudioWorkletProcessor, registerProcessor */
class MicrophoneProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = new Float32Array(2048);
    this.used = 0;
    this.port.onmessage = (event) => {
      if (event.data === "flush") {
        this.flush();
        this.port.postMessage("flushed");
      }
    };
  }
  flush() {
    if (!this.used) return;
    const chunk = this.samples.slice(0, this.used);
    this.port.postMessage(chunk, [chunk.buffer]);
    this.used = 0;
  }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (channel) {
      for (const sample of channel) {
        this.samples[this.used++] = sample;
        if (this.used === this.samples.length) this.flush();
      }
    }
    return true;
  }
}
registerProcessor("lunaris-microphone", MicrophoneProcessor);
