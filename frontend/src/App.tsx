import { useEffect, useState } from 'react';
import { checkHealth } from './api';
import './App.css';

type Status = 'checking' | 'connected' | 'unreachable';

export default function App() {
  const [status, setStatus] = useState<Status>('checking');
  const [nodeId, setNodeId] = useState<string | null>(null);

  useEffect(() => {
    checkHealth()
      .then((res) => {
        setStatus(res.ok ? 'connected' : 'unreachable');
        setNodeId(res.node ?? null);
      })
      .catch(() => setStatus('unreachable'));
  }, []);

  return (
    <div className="app">
      <h1>BODDOS</h1>
      <p className={`status status-${status}`}>
        backend: {status}
        {nodeId && ` (${nodeId})`}
      </p>
    </div>
  );
}
