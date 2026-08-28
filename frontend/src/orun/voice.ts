/**
 * Continuous wake-word voice loop: mirrors the state machine the old
 * boddos/ui/app.js "Voice" controller used (off → wake → active → wake…),
 * rebuilt as a plain class so it's reusable outside that one page.
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
}

function getSpeechRecognition(): any {
  return (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
}

export function speechRecognitionSupported(): boolean {
  return !!getSpeechRecognition();
}

export class VoiceController {
  mode: VoiceMode = 'off';
  private recognition: any = null;
  private opts: VoiceOptions;

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

  start(mode: 'wake' | 'active' = 'wake'): void {
    const SR = getSpeechRecognition();
    if (!SR) return;
    this.stop();
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = false;
    rec.lang = 'en-US';

    rec.onresult = (e: any) => {
      const last = e.results[e.results.length - 1];
      const text: string = last?.[0]?.transcript?.trim() ?? '';
      if (!text) return;

      if (this.mode === 'wake') {
        const re = this.wakeRegex();
        if (!re.test(text)) return;
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
    rec.onerror = () => {
      /* no-speech / audio-capture errors are routine in continuous mode */
    };

    this.recognition = rec;
    this.setMode(mode);
    rec.start();
  }

  stop(): void {
    this.setMode('off');
    try {
      this.recognition?.stop();
    } catch {
      /* not running */
    }
    this.recognition = null;
  }

  private setMode(mode: VoiceMode): void {
    this.mode = mode;
    this.opts.onModeChange?.(mode);
  }
}
