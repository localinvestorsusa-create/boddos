import { useEffect, useRef, useState } from 'react';
import { fetchUiConfig, speakBackend, streamChat, type ChatMessage, type ToolActivity, type UiConfig } from '../api';
import { playAudio, speak, type MicLevel, type PulseLevel } from '../orun/audio';
import { VoiceController, voiceInputSupported, type VoiceMode } from '../orun/voice';
import ScreenControl from './ScreenControl';
import MeshPanel from './MeshPanel';
import FinderPanel from './FinderPanel';
import SkillPortal from './SkillPortal';
import MuscleMemoryGrid from './MuscleMemoryGrid';
import HomeAutomationPanel from './HomeAutomationPanel';
import PlannerPanel from './PlannerPanel';
import BriefingPanel from './BriefingPanel';
import TabNav from './TabNav';
import './sections.css';
import './ogun.css';

type SupportTab = 'skills' | 'mesh' | 'finder' | 'screen' | 'home' | 'planner' | 'briefing';

const SUPPORT_TABS: { id: SupportTab; label: string }[] = [
  { id: 'skills', label: 'New wishes' },
  { id: 'mesh', label: 'Mesh' },
  { id: 'finder', label: 'Finder' },
  { id: 'screen', label: 'Screen' },
  { id: 'home', label: 'Home' },
  { id: 'planner', label: 'Planner' },
  { id: 'briefing', label: 'Briefing' },
];

interface OrunmilaProps {
  micLevel: MicLevel;
  replyLevel: PulseLevel;
}

interface ToolLogEntry {
  name: string;
  ok?: boolean; // undefined while the call is still running
}

interface Turn {
  role: 'user' | 'assistant';
  text: string;
  tools?: ToolLogEntry[];
}

function humanizeTool(name: string): string {
  return name.replace(/_/g, ' ');
}

export default function Orunmila({ micLevel, replyLevel }: OrunmilaProps) {
  const [config, setConfig] = useState<UiConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [voiceMode, setVoiceMode] = useState<VoiceMode>('off');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [ttsNotice, setTtsNotice] = useState<string | null>(null);
  const [skillsVersion, setSkillsVersion] = useState(0);
  const [supportTab, setSupportTab] = useState<SupportTab>('skills');
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

  /** Speaks `text` aloud through the backend's Piper voice, falling back to
   * the browser's own synthesizer (with a one-line notice explaining why)
   * when Piper isn't set up on this node yet. Shared by real replies and
   * the instant wake-word acknowledgement below. */
  function announce(text: string) {
    speakBackend(text, config?.tts_voice)
      .then((bytes) => {
        setTtsNotice(null);
        return playAudio(bytes, replyLevel);
      })
      .catch((e) => {
        console.warn('backend voice unavailable, falling back to browser voice:', e);
        setTtsNotice(
          `Using the browser's built-in voice — Piper isn't set up on the backend yet (${e}). ` +
            'See README.md "Natural voice replies" for the one-time setup.',
        );
        speak(text, () => replyLevel.bump(0.4));
      });
  }

  async function send(text: string) {
    const clean = text.trim();
    if (!clean || busy) return;
    setDraft('');
    const merged: Turn[] = [...turns, { role: 'user', text: clean }];
    const history: ChatMessage[] = merged.map((t) => ({ role: t.role, content: t.text }));
    setTurns((prev) => [...prev, { role: 'user', text: clean }, { role: 'assistant', text: '' }]);
    setBusy(true);
    try {
      const full = await streamChat(
        history,
        (chunk) => {
          replyLevel.bump(0.25 + Math.random() * 0.15);
          setTurns((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, text: last.text + chunk };
            return next;
          });
        },
        undefined,
        (activity: ToolActivity) => {
          setTurns((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            const tools = [...(last.tools ?? [])];
            if (activity.kind === 'call') {
              tools.push({ name: activity.name });
            } else {
              const openIdx = tools.map((t) => t.ok === undefined && t.name === activity.name).lastIndexOf(true);
              if (openIdx !== -1) tools[openIdx] = { ...tools[openIdx], ok: activity.ok };
            }
            next[next.length - 1] = { ...last, tools };
            return next;
          });
        },
      );
      announce(full);
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
      onError: setVoiceError,
      // Instant audible confirmation the moment the wake word lands, so
      // there's never dead air between "did it hear me?" and the actual
      // reply — it doesn't wait for you to finish speaking to react.
      onWake: () => announce(config.greeting || 'Yes?'),
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
    setVoiceError(null);
    micLevel.start().catch((e) => setVoiceError(`Couldn't access the microphone: ${e}`));
    voiceRef.current?.start('wake');
  }

  const name = config?.assistant_name ?? 'Orunmila';
  const micLabel = !voiceInputSupported()
    ? '🎙 voice input unavailable in this browser'
    // busy checked before voiceMode: once a command is captured, voiceMode
    // drops straight back to "wake" so it can listen for the next one —
    // without this, the button would silently look idle mid-request.
    : busy
      ? '🤔 thinking…'
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
              {t.tools && t.tools.length > 0 && (
                <ul className="tool-log">
                  {t.tools.map((tl, j) => (
                    <li key={j} className={tl.ok === undefined ? 'running' : tl.ok ? 'ok' : 'error'}>
                      <span className="tool-mark">{tl.ok === undefined ? '…' : tl.ok ? '✓' : '✗'}</span>
                      {humanizeTool(tl.name)}
                    </li>
                  ))}
                </ul>
              )}
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
            disabled={!voiceInputSupported()}
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
        {voiceError && <p className="section-warn voice-error">{voiceError}</p>}
        {ttsNotice && <p className="section-warn voice-error">{ttsNotice}</p>}
      </div>

      <TabNav tabs={SUPPORT_TABS} active={supportTab} onChange={(id) => setSupportTab(id as SupportTab)} />
      {supportTab === 'skills' && (
        <>
          <SkillPortal onSaved={() => setSkillsVersion((v) => v + 1)} />
          <MuscleMemoryGrid refreshKey={skillsVersion} />
        </>
      )}
      {supportTab === 'mesh' && <MeshPanel />}
      {supportTab === 'finder' && <FinderPanel />}
      {supportTab === 'screen' && <ScreenControl />}
      {supportTab === 'home' && <HomeAutomationPanel />}
      {supportTab === 'planner' && <PlannerPanel />}
      {supportTab === 'briefing' && <BriefingPanel />}
    </div>
  );
}
