import { useEffect, useRef, useState } from 'react';
import { fetchUiConfig, streamChat, type ChatMessage, type UiConfig } from '../api';
import { speak, type MicLevel, type PulseLevel } from '../orun/audio';
import './sections.css';

interface OrunmilaProps {
  micLevel: MicLevel;
  replyLevel: PulseLevel;
}

interface Turn {
  role: 'user' | 'assistant';
  text: string;
}

export default function Orunmila({ micLevel, replyLevel }: OrunmilaProps) {
  const [config, setConfig] = useState<UiConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    fetchUiConfig()
      .then(setConfig)
      .catch((e) => setConfigError(String(e)));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns]);

  async function send(text: string) {
    const clean = text.trim();
    if (!clean || busy) return;
    setDraft('');
    const merged: Turn[] = [...turns, { role: 'user', text: clean }];
    const history: ChatMessage[] = merged.map((t) => ({ role: t.role, content: t.text }));
    setTurns((prev) => [...prev, { role: 'user', text: clean }, { role: 'assistant', text: '' }]);
    setBusy(true);
    try {
      const full = await streamChat(history, (chunk) => {
        replyLevel.bump(0.25 + Math.random() * 0.15);
        setTurns((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', text: next[next.length - 1].text + chunk };
          return next;
        });
      });
      speak(full, () => replyLevel.bump(0.4));
    } catch (e) {
      setTurns((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: 'assistant',
          text: `[couldn't reach the backend — is the BODDOS node running on :8000? (${e})]`,
        };
        return next;
      });
    } finally {
      setBusy(false);
    }
  }

  function toggleListen() {
    const SpeechRecognition = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    if (listening) {
      recognitionRef.current?.stop();
      micLevel.stop();
      setListening(false);
      return;
    }
    micLevel.start().catch(() => {});
    if (!SpeechRecognition) {
      setListening(true);
      return;
    }
    const rec = new SpeechRecognition();
    rec.continuous = false;
    rec.interimResults = false;
    rec.lang = 'en-US';
    rec.onresult = (e: any) => {
      const text = e.results[0]?.[0]?.transcript ?? '';
      if (text) send(text);
    };
    rec.onend = () => {
      setListening(false);
      micLevel.stop();
    };
    rec.onerror = () => {
      setListening(false);
      micLevel.stop();
    };
    recognitionRef.current = rec;
    rec.start();
    setListening(true);
  }

  const name = config?.assistant_name ?? 'Orunmila';

  return (
    <div className="section orunmila">
      <header className="section-head">
        <span className="section-eyebrow">Wishes</span>
        <h1>{name}</h1>
        <p className="section-dek">
          {config?.greeting ?? 'History, models, and every tool across the workspace, in one place.'}
        </p>
        {configError && (
          <p className="section-warn">Backend not reachable at :8000 yet — {configError}</p>
        )}
      </header>

      <div className="chat-panel">
        <div className="chat-scroll" ref={scrollRef}>
          {turns.length === 0 && (
            <p className="chat-empty">Ask for anything — a plan, a tool, a status check. Speak or type.</p>
          )}
          {turns.map((t, i) => (
            <div key={i} className={`bubble ${t.role}`}>
              <span className="bubble-role">{t.role === 'user' ? 'you' : name.toLowerCase()}</span>
              <p>{t.text || (busy && i === turns.length - 1 ? '…' : '')}</p>
            </div>
          ))}
        </div>
        <form
          className="chat-input"
          onSubmit={(e) => {
            e.preventDefault();
            send(draft);
          }}
        >
          <button
            type="button"
            className={`mic-btn ${listening ? 'live' : ''}`}
            onClick={toggleListen}
            aria-pressed={listening}
            aria-label="Toggle voice input"
          >
            {listening ? '● listening' : '🎙'}
          </button>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={`Speak to ${name}, or type here…`}
          />
          <button type="submit" disabled={busy || !draft.trim()}>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
