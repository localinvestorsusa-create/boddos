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

export interface RouteStep {
  instruction: string;
  distance_m: number;
  duration_s: number;
}

export interface RouteGeometry {
  type: 'LineString';
  coordinates: [number, number][]; // [lon, lat]
}

export interface DirectionsResult {
  ok: boolean;
  error?: string;
  profile?: string;
  distance_m?: number;
  duration_s?: number;
  geometry?: RouteGeometry;
  steps?: RouteStep[];
  destination?: string;
  destination_lat?: number;
  destination_lon?: number;
}

export async function fetchDirections(
  fromLat: number,
  fromLon: number,
  destination: string,
  profile: 'walking' | 'driving' | 'cycling' = 'walking',
): Promise<DirectionsResult> {
  const res = await fetch('/api/esu/directions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from_lat: fromLat, from_lon: fromLon, destination, profile }),
  });
  return res.json();
}

export interface VisionResult {
  ok: boolean;
  error?: string;
  analysis?: string;
}

export async function analyzeImage(imageB64: string, prompt: string): Promise<VisionResult> {
  const res = await fetch('/api/vision', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_b64: imageB64, prompt }),
  });
  return res.json();
}

export interface ModelResult {
  ok: boolean;
  error?: string;
  stl_b64?: string;
  image_b64?: string;
  facets: number;
  log?: string;
}

export async function buildModel(scad: string): Promise<ModelResult> {
  const res = await fetch('/api/ogun/model', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scad }),
  });
  return res.json();
}

export interface CombustionResult {
  ok: boolean;
  error?: string;
  flame_temperature_k?: number;
  products: Record<string, number>;
  warnings: string[];
}

export async function checkCombustion(
  mixture: string,
  initialTempK = 300,
  pressureAtm = 1,
): Promise<CombustionResult> {
  const res = await fetch('/api/ogun/combustion', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mixture, initial_temp_k: initialTempK, pressure_atm: pressureAtm }),
  });
  return res.json();
}

export interface CircuitComponent {
  type: 'R' | 'C' | 'L';
  a: string;
  b: string;
  value: number;
}

export interface CircuitResult {
  ok: boolean;
  error?: string;
  netlist?: string;
  time_s: number[];
  traces: Record<string, number[]>;
}

export async function simulateCircuit(
  components: CircuitComponent[],
  volts: number,
  traceNodes: string[],
  stepUs = 1,
  endMs = 5,
): Promise<CircuitResult> {
  const res = await fetch('/api/ogun/circuit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      components,
      source: { node_pos: 'in', node_neg: '0', volts },
      trace_nodes: traceNodes,
      step_us: stepUs,
      end_ms: endMs,
    }),
  });
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
