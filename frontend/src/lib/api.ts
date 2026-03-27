// src/lib/api.ts

const BASE = '/api';

export async function createSession(files: File[]): Promise<{ session_id: string; files: string[] }> {
  const form = new FormData();
  for (const f of files) form.append('files', f);
  const res = await fetch(`${BASE}/sessions`, { method: 'POST', body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }
  return res.json();
}

export async function runSession(sessionId: string): Promise<void> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/run`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to start (${res.status})`);
  }
}

export function streamSession(sessionId: string): EventSource {
  // EventSource bypasses the Next.js proxy — must hit FastAPI directly
  const backendUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  return new EventSource(`${backendUrl}/api/sessions/${sessionId}/stream`);
}

export async function getResults(sessionId: string) {
  const res = await fetch(`${BASE}/sessions/${sessionId}/results`);
  if (!res.ok) throw new Error(`Results not ready (${res.status})`);
  return res.json();
}

export async function getStatus(sessionId: string) {
  const res = await fetch(`${BASE}/sessions/${sessionId}/status`);
  if (!res.ok) throw new Error(`Status check failed (${res.status})`);
  return res.json();
}

export function fixedFileUrl(sessionId: string, filename: string): string {
  return `${BASE}/sessions/${sessionId}/files/${filename}`;
}

export function reportPdfUrl(sessionId: string): string {
  return `${BASE}/sessions/${sessionId}/report.pdf`;
}
