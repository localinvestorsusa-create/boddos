export interface HealthResult {
  ok: boolean;
  node?: string;
}

export async function checkHealth(): Promise<HealthResult> {
  const res = await fetch('/health');
  return res.json();
}
