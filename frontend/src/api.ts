export interface UiConfig {
  assistant_name: string;
  wake_words: string[];
  greeting: string;
  vision_model: string;
  push_enabled: boolean;
}

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export async function fetchUiConfig(): Promise<UiConfig> {
  const res = await fetch('/api/ui-config');
  if (!res.ok) throw new Error(`ui-config ${res.status}`);
  return res.json();
}

/**
 * Streams a reply from /api/chat/stream (server-sent events) and reports
 * each token to onToken as it arrives. Resolves with the full reply text.
 */
export async function streamChat(
  messages: ChatMessage[],
  onToken: (chunk: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`chat/stream ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let full = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const payload = line.replace(/^data:\s*/, '').trim();
      if (!payload) continue;
      try {
        const evt = JSON.parse(payload);
        if (typeof evt.t === 'string') {
          full += evt.t;
          onToken(evt.t);
        }
        if (evt.done) return full;
      } catch {
        // ignore malformed keepalive lines
      }
    }
  }
  return full;
}
