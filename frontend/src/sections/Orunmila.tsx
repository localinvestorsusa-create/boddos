import { useEffect, useRef, useState } from 'react';
import { fetchUiConfig, streamChat, type ChatMessage, type UiConfig } from '../api';
import { speak, type MicLevel, type PulseLevel } from '../orun/audio';
import { VoiceController, speechRecognitionSupported, type VoiceMode } from '../orun/voice';
import ScreenControl from './ScreenControl';
import MeshPanel from './MeshPanel';
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
  const [voiceMode, setVoiceMode] = useState<VoiceMode>('off');
  const scrollRef = useRef<HTMLDivElement>(null);
  const voiceRef = useRef<VoiceController | null>(null);
  const sendRef = useRef<(text: string) => void>(() => {});

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

  // Keep a live reference so the voice controller (created once) always
  // calls the latest `send`, which closes over current turns/busy state.
  useEffect(() => {
    sendRef.current = send;
  });

  useEffect(() => {
    if (!config) return;
    voiceRef.current = new VoiceController({
      wakeWords: config.wake_words,
      onCommand: (text) => sendRef.current(text),
      onModeChange: setVoiceMode,
    });
    return () => voiceRef.current?.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config?.wake_words.join('|')]);

  function toggleVoice() {
    if (voiceMode !== 'off') {
      voiceRef.current?.stop();
      micLevel.stop();
      return;
    }
    micLevel.start().catch(() => {});
    voiceRef.current?.start('wake');
  }

  const name = config?.assistant_name ?? 'Orunmila';
  const micLabel = !speechRecognitionSupported()
    ? '🎙 no browser voice support'
    : voiceMode === 'active'
      ? '🔴 listening…'
      : voiceMode === 'wake'
        ? `😴 waiting for "hey ${name.toLowerCase()}"`
        : `🎙 say "hey ${name.toLowerCase()}"`;

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
            className={`mic-btn ${voiceMode !== 'off' ? 'live' : ''}`}
            onClick={toggleVoice}
            aria-pressed={voiceMode !== 'off'}
            aria-label="Toggle wake-word listening"
            disabled={!speechRecognitionSupported()}
          >
            {micLabel}
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

      <MeshPanel />
      <ScreenControl />
    </div>
  );
}
