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

export interface HardwareReport {
  cpu_model: string;
  cpu_cores: number;
  ram_gb: number;
  gpu_vendor: string | null;
  gpu_name: string | null;
  vram_gb: number;
  has_gpu: boolean;
  os_name: string;
  recommended_model: string;
  recommended_vision_model: string;
  notes: string[];
}

export async function fetchHardware(): Promise<HardwareReport> {
  const res = await fetch('/api/hardware');
  if (!res.ok) throw new Error(`hardware ${res.status}`);
  return res.json();
}

export interface MeshNode {
  id: string;
  name: string;
  role: string;
  url: string;
  ram_gb: number;
  has_gpu: boolean;
  vram_gb: number;
  gpu_name: string;
  models: string[];
  last_seen: number;
}

export async function fetchMeshNodes(): Promise<MeshNode[]> {
  const res = await fetch('/mesh/nodes');
  if (!res.ok) throw new Error(`mesh/nodes ${res.status}`);
  const data = await res.json();
  return data.nodes;
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

export interface BeamResult {
  ok: boolean;
  error?: string;
  tip_deflection_m: number;
  analytical_deflection_m: number;
  agreement_pct: number;
  max_stress_note?: string;
  nodes: number;
  elements: number;
}

export async function simulateBeam(
  lengthM: number,
  widthM: number,
  heightM: number,
  tipForceN: number,
  material: string,
): Promise<BeamResult> {
  const res = await fetch('/api/ogun/beam', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ length_m: lengthM, width_m: widthM, height_m: heightM, tip_force_n: tipForceN, material }),
  });
  return res.json();
}

export interface RocketResult {
  ok: boolean;
  error?: string;
  apogee_m: number;
  max_speed_ms: number;
  max_acceleration_ms2: number;
  time_to_apogee_s: number;
  warnings: string[];
}

export async function simulateRocket(params: {
  total_impulse_ns: number;
  burn_time_s: number;
  propellant_mass_kg: number;
  rocket_dry_mass_kg: number;
  rocket_radius_m: number;
}): Promise<RocketResult> {
  const res = await fetch('/api/ogun/rocket', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return res.json();
}

export interface SequenceResult {
  ok: boolean;
  error?: string;
  kind: string;
  length: number;
  gc_fraction?: number;
  molecular_weight_da?: number;
  translated_protein?: string;
  protein_molecular_weight_da?: number;
  instability_index?: number;
  aromaticity?: number;
}

export async function analyzeSequence(sequence: string): Promise<SequenceResult> {
  const res = await fetch('/api/ogun/sequence', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sequence }),
  });
  return res.json();
}

export interface DynamicsResult {
  ok: boolean;
  error?: string;
  platform: string;
  energy_kj_mol: number[];
  max_energy_drift_pct: number;
}

export async function runParticleDynamics(particleCount: number): Promise<DynamicsResult> {
  const res = await fetch('/api/ogun/dynamics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ particle_count: particleCount, steps: 1500 }),
  });
  return res.json();
}

export interface MaterialMatch {
  material_id: string;
  formula: string;
  density_g_cm3: number | null;
  band_gap_ev: number | null;
  energy_above_hull_ev: number | null;
  crystal_system: string | null;
}

export interface MaterialResult {
  ok: boolean;
  error?: string;
  matches: MaterialMatch[];
}

export async function lookupMaterial(formula: string): Promise<MaterialResult> {
  const res = await fetch('/api/ogun/material', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ formula }),
  });
  return res.json();
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
