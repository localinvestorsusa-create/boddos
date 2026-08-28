/**
 * Lightweight, render-free audio level sources. Each exposes a mutable
 * `.level` (0..1) read directly inside a useFrame loop, so the globe can
 * animate at 60fps without funneling audio data through React state.
 */

export class MicLevel {
  level = 0;
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private raf = 0;

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.ctx = new AudioContext();
    const source = this.ctx.createMediaStreamSource(this.stream);
    const analyser = this.ctx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);

    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sumSquares = 0;
      for (let i = 0; i < data.length; i++) {
        const centered = (data[i] - 128) / 128;
        sumSquares += centered * centered;
      }
      const rms = Math.sqrt(sumSquares / data.length);
      // A relaxed voice sits well under 1.0 RMS; scale up so it reads clearly.
      this.level = Math.min(1, rms * 4.5);
      this.raf = requestAnimationFrame(tick);
    };
    tick();
  }

  stop(): void {
    cancelAnimationFrame(this.raf);
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close();
    this.ctx = null;
    this.stream = null;
    this.level = 0;
  }
}

/** An event-driven level that spikes on bump() and decays each frame. */
export class PulseLevel {
  level = 0;
  private raf = 0;
  private running = false;

  bump(amount = 0.55): void {
    this.level = Math.min(1, this.level + amount);
    if (!this.running) this.loop();
  }

  private loop(): void {
    this.running = true;
    const tick = () => {
      this.level *= 0.88;
      if (this.level < 0.005) {
        this.level = 0;
        this.running = false;
        return;
      }
      this.raf = requestAnimationFrame(tick);
    };
    tick();
  }

  stop(): void {
    cancelAnimationFrame(this.raf);
    this.running = false;
    this.level = 0;
  }
}

/** Speaks text aloud with the browser's built-in synthesizer, bumping a
 * PulseLevel on each word boundary so the reply strip has something real
 * to react to (no local TTS server required for this preview). */
export function speak(text: string, onWord: () => void, onDone?: () => void): void {
  if (!('speechSynthesis' in window) || !text.trim()) {
    onDone?.();
    return;
  }
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate = 1.02;
  utter.onboundary = () => onWord();
  utter.onstart = () => onWord();
  utter.onend = () => onDone?.();
  utter.onerror = () => onDone?.();
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter);
}
