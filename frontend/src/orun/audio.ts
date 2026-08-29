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

/** Plays real synthesized audio (from the backend's Piper voice engine)
 * through the Web Audio API, driving `level` from the actual waveform —
 * same RMS analysis MicLevel uses for the mic — so the reply strip moves
 * in sync with what's really being said, not a guessed word-boundary bump. */
export async function playAudio(bytes: ArrayBuffer, level: PulseLevel, onDone?: () => void): Promise<void> {
  const ctx = new AudioContext();
  const buffer = await ctx.decodeAudioData(bytes);
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  source.connect(analyser);
  analyser.connect(ctx.destination);
  const data = new Uint8Array(analyser.frequencyBinCount);
  let raf = 0;

  const tick = () => {
    analyser.getByteTimeDomainData(data);
    let sumSquares = 0;
    for (let i = 0; i < data.length; i++) {
      const centered = (data[i] - 128) / 128;
      sumSquares += centered * centered;
    }
    const rms = Math.sqrt(sumSquares / data.length);
    level.level = Math.min(1, rms * 4.5);
    raf = requestAnimationFrame(tick);
  };

  source.onended = () => {
    cancelAnimationFrame(raf);
    level.level = 0;
    void ctx.close();
    onDone?.();
  };
  source.start();
  tick();
}

/** Fallback voice: the browser's own built-in synthesizer, used only when
 * the backend's Piper voice isn't set up yet (see playAudio above, and
 * README.md "Natural voice replies"). Bumps a PulseLevel on each word
 * boundary since there's no real waveform to analyze here. */
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
