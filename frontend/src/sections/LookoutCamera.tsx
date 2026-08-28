import { useRef, useState } from 'react';
import { analyzeImage } from '../api';

const HAZARD_PROMPT =
  "You're describing a scene for someone walking with their eyes on the path ahead. " +
  'Note obstacles, curbs/steps, traffic, crowd density, and anything else relevant to ' +
  'moving through it safely. Be concise — a few sentences.';

export default function LookoutCamera() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setActive(true);
    } catch (e) {
      setError(`Camera unavailable: ${e}`);
    }
  }

  function stop() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setActive(false);
    setAnalysis(null);
  }

  async function capture() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);
    const b64 = canvas.toDataURL('image/jpeg', 0.85).split(',')[1];
    setBusy(true);
    setAnalysis(null);
    try {
      const res = await analyzeImage(b64, HAZARD_PROMPT);
      setAnalysis(res.ok ? res.analysis || '(no description returned)' : `Couldn't analyze: ${res.error}`);
    } catch (e) {
      setAnalysis(`Couldn't analyze: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lookout">
      <div className="lookout-head">
        <h3>Lookout</h3>
        <button onClick={active ? stop : start}>{active ? 'Stop camera' : 'Start camera'}</button>
      </div>
      {error && <p className="section-warn">{error}</p>}
      {active && (
        <div className="lookout-body">
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video ref={videoRef} muted playsInline />
          <button onClick={capture} disabled={busy}>
            {busy ? 'Looking…' : 'What do you see?'}
          </button>
        </div>
      )}
      {analysis && <p className="screen-note">{analysis}</p>}
    </div>
  );
}
