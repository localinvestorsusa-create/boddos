/**
 * Continuous wake-word voice loop, driven by the backend's own Vosk speech
 * engine over a WebSocket — not the browser's SpeechRecognition API, which
 * on Chrome doesn't actually run locally (it streams audio to Google's own
 * servers) and doesn't exist at all on Firefox. This talks to a small,
 * fast, fully offline recognizer instead (see boddos/voice/stt.py):
 * recognition speed never depends on the chat model, audio never leaves
 * the machine, and it works in any browser that can do getUserMedia +
 * WebSocket.
 *
 * Falls back automatically to the browser's own SpeechRecognition (when
 * present) if the backend's Vosk model isn't downloaded yet — same
 * fallback philosophy as the Piper voice-output side (see api.speakBackend).
 *
 * "wake": listening only for the wake phrase ("hey ori").
 * "active": the wake phrase just fired; the next utterance is a command.
 * After a command is handled, it drops back to "wake" automatically —
 * continuous listening, not push-to-talk.
 */

export type VoiceMode = 'off' | 'wake' | 'active';

interface VoiceOptions {
  wakeWords: string[];
  onCommand: (text: string) => void;
  onModeChange?: (mode: VoiceMode) => void;
  /** Fired for errors worth telling the user about — permission denial or
   * no audio device — not the routine no-speech timeouts a continuous
   * recognizer hits constantly while just sitting there listening. */
  onError?: (message: string) => void;
  /** Fired the instant the wake word itself is heard, before whatever
   * follows it is known — the cue to give an immediate audible/visual
   * "yes, go ahead" instead of leaving the user unsure it heard them. */
  onWake?: () => void;
}

const _ACTIONABLE_BROWSER_ERRORS: Record<string, string> = {
  'not-allowed': 'Microphone access was denied — allow it in your browser\'s site settings, then click the mic button again.',
  'service-not-allowed': 'The browser blocked speech recognition for this page — check site permissions.',
  'audio-capture': 'No microphone found — check it\'s connected and not in use by another app.',
  network: 'Speech recognition needs a network connection to work (it runs through the browser, not this server) — check your connection.',
};

function getBrowserSpeechRecognition(): any {
  return (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
}

export function voiceInputSupported(): boolean {
  const hasMic = typeof navigator.mediaDevices?.getUserMedia === 'function' && 'WebSocket' in window;
  return hasMic || !!getBrowserSpeechRecognition();
}

export class VoiceController {
  mode: VoiceMode = 'off';
  private opts: VoiceOptions;

  // Vosk-over-WebSocket engine
  private ws: WebSocket | null = null;
  private audioCtx: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null;
  private micStream: MediaStream | null = null;

  // Browser SpeechRecognition fallback
  private fallbackRec: any = null;

  constructor(opts: VoiceOptions) {
    this.opts = opts;
  }

  private wakeRegex(): RegExp {
    const alts = this.opts.wakeWords
      .map((w) => w.trim())
      .filter(Boolean)
      .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
      .join('|');
    return new RegExp(`\\b(${alts || 'hey ori'})\\b`, 'i');
  }

  /** Shared by both engines: a finalized transcript just came in — decide
   * whether it's the wake word, or a command following it. */
  private handleTranscript(text: string): void {
    if (!text) return;
    if (this.mode === 'wake') {
      const re = this.wakeRegex();
      if (!re.test(text)) return;
      this.opts.onWake?.();
      this.setMode('active');
      const after = text.replace(re, '').trim();
      if (after) {
        this.opts.onCommand(after);
        this.setMode('wake');
      }
    } else if (this.mode === 'active') {
      this.opts.onCommand(text);
      this.setMode('wake');
    }
  }

  async start(mode: 'wake' | 'active' = 'wake'): Promise<void> {
    this.stop();
    this.setMode(mode);
    const ok = await this.startVosk();
    if (!ok) this.startBrowserFallback();
  }

  stop(): void {
    this.setMode('off');
    this.teardownVosk();
    try {
      this.fallbackRec?.stop();
    } catch {
      /* not running */
    }
    this.fallbackRec = null;
  }

  private setMode(mode: VoiceMode): void {
    this.mode = mode;
    this.opts.onModeChange?.(mode);
  }

  // ------------------------- Vosk over WebSocket -------------------------

  private async startVosk(): Promise<boolean> {
    if (typeof navigator.mediaDevices?.getUserMedia !== 'function' || !('WebSocket' in window)) return false;

    try {
      this.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      this.opts.onError?.(`Couldn't access the microphone: ${e}`);
      return false;
    }

    const AudioCtx: typeof AudioContext =
      (window as any).AudioContext ?? (window as any).webkitAudioContext;
    try {
      // Vosk's models expect 16kHz mono; most browsers honor this request,
      // but the *actual* rate is read back and sent to the backend below so
      // recognition stays correct even when a platform doesn't grant it.
      this.audioCtx = new AudioCtx({ sampleRate: 16000 });
    } catch {
      this.teardownVosk();
      return false;
    }
    const rate = Math.round(this.audioCtx.sampleRate);

    return new Promise<boolean>((resolve) => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(`${proto}://${location.host}/ws/voice/stt?rate=${rate}`);
      ws.binaryType = 'arraybuffer';
      let settled = false;

      const fail = () => {
        if (settled) return;
        settled = true;
        this.teardownVosk();
        resolve(false);
      };

      ws.onopen = () => {
        if (!this.audioCtx || !this.micStream) return;
        const source = this.audioCtx.createMediaStreamSource(this.micStream);
        // ScriptProcessorNode is deprecated but universally supported and
        // sufficient at this data rate — an AudioWorklet would need a
        // separately-served module file for a marginal gain here.
        const processor = this.audioCtx.createScriptProcessor(4096, 1, 1);
        processor.onaudioprocess = (e) => {
          if (ws.readyState !== WebSocket.OPEN) return;
          const input = e.inputBuffer.getChannelData(0);
          const pcm = new Int16Array(input.length);
          for (let i = 0; i < input.length; i++) {
            const s = Math.max(-1, Math.min(1, input[i]));
            pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          ws.send(pcm.buffer);
        };
        source.connect(processor);
        // Must be connected to a destination for onaudioprocess to fire in
        // some browsers; the output buffer is left at silence (zeros).
        processor.connect(this.audioCtx.destination);
        this.processor = processor;
        if (!settled) {
          settled = true;
          this.ws = ws;
          resolve(true);
        }
      };

      ws.onmessage = (ev) => {
        let msg: any;
        try {
          msg = JSON.parse(ev.data as string);
        } catch {
          return;
        }
        if (msg.error) {
          // Vosk isn't set up on the backend yet — fall back instead of
          // going silent. This can arrive after the connection already
          // "succeeded" (onopen fired before the model-load check failed).
          this.opts.onError?.(
            `Using the browser's built-in speech recognition — Vosk isn't set up on the backend yet (${msg.error}). ` +
              'See README.md "Fast local speech recognition" for the one-time setup.',
          );
          fail();
          if (this.mode !== 'off') this.startBrowserFallback();
          return;
        }
        if (typeof msg.final === 'string') this.handleTranscript(msg.final.trim());
      };

      ws.onerror = () => fail();
      ws.onclose = () => {
        if (!settled) fail();
      };
    });
  }

  private teardownVosk(): void {
    this.processor?.disconnect();
    this.processor = null;
    this.micStream?.getTracks().forEach((t) => t.stop());
    this.micStream = null;
    if (this.audioCtx) void this.audioCtx.close();
    this.audioCtx = null;
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.close();
    this.ws = null;
  }

  // ---------------------- browser SpeechRecognition fallback ----------------------

  private startBrowserFallback(): void {
    const SR = getBrowserSpeechRecognition();
    if (!SR) {
      this.opts.onError?.(
        'No local speech engine set up yet, and this browser has no built-in fallback either — ' +
          'see README.md "Fast local speech recognition".',
      );
      this.setMode('off');
      return;
    }
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = false;
    rec.lang = 'en-US';

    rec.onresult = (e: any) => {
      const last = e.results[e.results.length - 1];
      const text: string = last?.[0]?.transcript?.trim() ?? '';
      this.handleTranscript(text);
    };
    rec.onend = () => {
      // Browsers stop a recognizer after a pause; keep the loop alive for
      // as long as voice mode is meant to be on.
      if (this.mode !== 'off') {
        try {
          rec.start();
        } catch {
          /* already running or the tab lost focus — next onend retries */
        }
      }
    };
    rec.onerror = (e: any) => {
      const message = _ACTIONABLE_BROWSER_ERRORS[e?.error];
      if (message) this.opts.onError?.(message);
      /* everything else (no-speech, aborted) is routine in continuous mode */
    };

    this.fallbackRec = rec;
    rec.start();
  }
}
