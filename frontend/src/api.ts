export interface UiConfig {
  assistant_name: string;
  wake_words: string[];
  greeting: string;
  vision_model: string;
  push_enabled: boolean;
  tts_enabled: boolean;
  tts_voice: string;
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

/** Synthesizes speech through the backend's Piper voice engine and returns
 * the raw WAV bytes to play. Throws (with the backend's own explanation,
 * e.g. "voice model not found — fetch it with ...") when Piper isn't set
 * up yet on that node — callers should fall back to the browser's own
 * speechSynthesis in that case, not treat it as fatal. */
export async function speakBackend(text: string, voice?: string): Promise<ArrayBuffer> {
  const res = await fetch('/api/voice/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(voice ? { text, voice } : { text }),
  });
  const contentType = res.headers.get('content-type') ?? '';
  if (!res.ok || !contentType.includes('audio')) {
    let detail = `voice/speak ${res.status}`;
    try {
      const data = await res.json();
      if (data?.error) detail = data.error;
    } catch {
      /* not JSON — keep the status-based message */
    }
    throw new Error(detail);
  }
  return res.arrayBuffer();
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

export interface PairStartResult {
  code: string;
  expires_in_s: number;
  my_url: string;
  my_name: string;
}

export async function startPairing(): Promise<PairStartResult> {
  const res = await fetch('/api/mesh/pair/start', { method: 'POST' });
  if (!res.ok) throw new Error(`pair/start ${res.status}`);
  return res.json();
}

export interface PairRedeemResult {
  ok: boolean;
  error?: string;
  connected_to?: string;
  peer_url?: string;
}

export async function redeemPairing(hostUrl: string, code: string): Promise<PairRedeemResult> {
  const res = await fetch('/api/mesh/pair/redeem', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ host_url: hostUrl, code }),
  });
  return res.json();
}

export interface FoundDevice {
  address: string;
  name: string;
  rssi: number;
}

export interface FinderScanResult {
  ok: boolean;
  error?: string;
  devices: FoundDevice[];
}

export async function scanForDevices(seconds = 4): Promise<FinderScanResult> {
  const res = await fetch('/api/finder/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seconds }),
  });
  return res.json();
}

export interface FinderStatus {
  ok: boolean;
  error?: string;
  tracking: boolean;
  address: string;
  name: string;
  rssi: number | null;
  proximity: string;
  trend: string;
  last_seen_s_ago: number | null;
}

export async function trackDevice(address: string, name: string): Promise<FinderStatus> {
  const res = await fetch('/api/finder/track', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address, name }),
  });
  return res.json();
}

export async function stopTrackingDevice(): Promise<FinderStatus> {
  const res = await fetch('/api/finder/stop', { method: 'POST' });
  return res.json();
}

export async function fetchFinderStatus(): Promise<FinderStatus> {
  const res = await fetch('/api/finder/status');
  return res.json();
}

export interface FetchRepoResult {
  ok: boolean;
  error?: string;
  source: string;
  files_packed: number;
  compressed: string;
  compressed_chars: number;
}

export async function fetchRepo(source: string): Promise<FetchRepoResult> {
  const res = await fetch('/api/skills/fetch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source }),
  });
  return res.json();
}

export interface BanditFinding {
  test: string;
  severity: string;
  confidence: string;
  line: number;
  text: string;
}

export interface ScanResult {
  ok: boolean;
  error?: string;
  ast_findings: string[];
  bandit_findings: BanditFinding[];
}

export async function scanSkillScript(script: string): Promise<ScanResult> {
  const res = await fetch('/api/skills/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script }),
  });
  return res.json();
}

export interface SkillInputSpec {
  name: string;
  label: string;
  type: 'text' | 'number';
}

export interface SkillRecord {
  slug: string;
  label: string;
  description: string;
  inputs: SkillInputSpec[];
  source_repo: string;
}

export async function saveSkill(
  script: string,
  manifest: { skill_id?: string; label: string; description?: string; inputs?: SkillInputSpec[] },
): Promise<{ ok: boolean; error?: string; skill?: SkillRecord }> {
  const res = await fetch('/api/skills/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script, manifest, confirm: true }),
  });
  return res.json();
}

export async function listSkills(): Promise<SkillRecord[]> {
  const res = await fetch('/api/skills');
  const data = await res.json();
  return data.skills;
}

export interface SkillRunResult {
  ok: boolean;
  error?: string;
  stdout: string;
  stderr: string;
  exit_code: number | null;
}

export async function runSkill(slug: string, inputs: Record<string, string>): Promise<SkillRunResult> {
  const res = await fetch(`/api/skills/${encodeURIComponent(slug)}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ inputs }),
  });
  return res.json();
}

export async function deleteSkill(slug: string): Promise<{ ok: boolean }> {
  const res = await fetch(`/api/skills/${encodeURIComponent(slug)}`, { method: 'DELETE' });
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

export interface ToolActivity {
  kind: 'call' | 'result';
  name: string;
  ok?: boolean;
}

/**
 * Streams a reply from /api/chat/stream (server-sent events) and reports
 * each token to onToken as it arrives. When the model uses a tool
 * mid-turn — building a model, checking the screen, running a skill, and
 * so on — each call/result is reported to onTool as it happens, so the UI
 * can narrate "using X..." live before the final answer streams in.
 * Resolves with the full reply text.
 */
/** No token, and no `done` event, for this long -> treat it as stuck rather
 * than leaving the UI's busy state (and the Send button) wedged forever.
 * Generous on purpose — a small model genuinely running slow on modest
 * hardware still needs room — but bounded, since a request that never
 * settles otherwise never lets go of `busy`. */
const CHAT_STREAM_TIMEOUT_MS = 180_000;

export async function streamChat(
  messages: ChatMessage[],
  onToken: (chunk: string) => void,
  signal?: AbortSignal,
  onTool?: (activity: ToolActivity) => void,
): Promise<string> {
  const controller = new AbortController();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', () => controller.abort(), { once: true });
  }
  const timeoutId = setTimeout(() => controller.abort(), CHAT_STREAM_TIMEOUT_MS);

  try {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages }),
      signal: controller.signal,
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
          if (evt.tool_call?.name) {
            onTool?.({ kind: 'call', name: evt.tool_call.name });
          }
          if (evt.tool_result?.name) {
            onTool?.({ kind: 'result', name: evt.tool_result.name, ok: evt.tool_result.ok });
          }
          if (evt.done) return full;
        } catch {
          // ignore malformed keepalive lines
        }
      }
    }
    return full;
  } catch (e) {
    if (controller.signal.aborted && !signal?.aborted) {
      throw new Error(
        `No reply after ${Math.round(CHAT_STREAM_TIMEOUT_MS / 1000)}s — the model may be too ` +
        'large for this machine (check Mesh for the recommended size) or Ollama has stopped responding.',
      );
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ----------------------------- smart home -----------------------------

export interface SmartDevice {
  ip: string;
  alias: string;
  model: string;
  is_on: boolean;
  device_type: string;
  is_dimmable: boolean;
  brightness: number | null;
  is_color: boolean;
  hsv: [number, number, number] | null;
}

export interface SmartHomeDiscoverResult {
  ok: boolean;
  error?: string;
  devices: SmartDevice[];
}

export async function discoverSmartDevices(): Promise<SmartHomeDiscoverResult> {
  const res = await fetch('/api/smarthome/discover');
  return res.json();
}

export interface ControlResult {
  ok: boolean;
  error?: string;
}

export async function controlSmartDevice(
  ip: string,
  action: 'on' | 'off' | 'brightness' | 'color',
  params: { level?: number; hue?: number; saturation?: number; value?: number } = {},
): Promise<ControlResult> {
  const res = await fetch('/api/smarthome/control', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ip, action, ...params }),
  });
  return res.json();
}

// -------------------------------- planner --------------------------------

export interface PlannerEvent {
  id: string;
  title: string;
  start_time: string;
  end_time: string;
  category: string;
  description: string;
}

export interface Alarm {
  id: string;
  time: string;
  label: string;
  enabled: boolean;
}

export interface PlannerTask {
  id: string;
  text: string;
  completed: boolean;
}

export async function fetchEvents(date?: string): Promise<PlannerEvent[]> {
  const url = date ? `/api/planner/events?date=${encodeURIComponent(date)}` : '/api/planner/events';
  const res = await fetch(url);
  const data = await res.json();
  return data.events;
}

export async function addEvent(
  title: string, start_time: string, end_time: string, category = 'general', description = '',
): Promise<PlannerEvent> {
  const res = await fetch('/api/planner/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, start_time, end_time, category, description }),
  });
  return res.json();
}

export async function deleteEvent(id: string): Promise<{ ok: boolean }> {
  const res = await fetch(`/api/planner/events/${id}`, { method: 'DELETE' });
  return res.json();
}

export async function fetchAlarms(): Promise<Alarm[]> {
  const res = await fetch('/api/planner/alarms');
  const data = await res.json();
  return data.alarms;
}

export async function addAlarm(time: string, label = ''): Promise<Alarm> {
  const res = await fetch('/api/planner/alarms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ time, label }),
  });
  return res.json();
}

export async function deleteAlarm(id: string): Promise<{ ok: boolean }> {
  const res = await fetch(`/api/planner/alarms/${id}`, { method: 'DELETE' });
  return res.json();
}

export async function fetchTasks(): Promise<PlannerTask[]> {
  const res = await fetch('/api/planner/tasks');
  const data = await res.json();
  return data.tasks;
}

export async function addTask(text: string): Promise<PlannerTask> {
  const res = await fetch('/api/planner/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  return res.json();
}

export async function toggleTask(id: string, completed: boolean): Promise<{ ok: boolean }> {
  const res = await fetch(`/api/planner/tasks/${id}/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ completed }),
  });
  return res.json();
}

export async function deleteTask(id: string): Promise<{ ok: boolean }> {
  const res = await fetch(`/api/planner/tasks/${id}`, { method: 'DELETE' });
  return res.json();
}

// --------------------------------- news ---------------------------------

export interface Headline {
  title: string;
  source: string;
  date: string;
  category: string;
  url: string;
  image: string | null;
}

export interface BriefingResult {
  ok: boolean;
  error?: string;
  curated: boolean;
  headlines: Headline[];
}

export async function fetchBriefing(useAi = true): Promise<BriefingResult> {
  const res = await fetch(`/api/news/briefing?use_ai=${useAi ? 'true' : 'false'}`);
  return res.json();
}
