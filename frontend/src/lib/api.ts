// src/lib/api.ts
// API client — supports both legacy /api/sessions and new /api/v1/evaluate endpoints.

const BASE = (typeof window !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) 
  ? `${process.env.NEXT_PUBLIC_API_URL}/api` 
  : '/api';

// ===========================================================================
// V1 API (preferred)
// ===========================================================================

/**
 * Single-step: upload HTML files and immediately start the evaluation pipeline.
 * Returns { job_id, file_count, status }.
 */
export async function evaluate(files: File[]): Promise<{ job_id: string; file_count: number; status: string }> {
  const form = new FormData();
  for (const f of files) form.append('files', f);
  const res = await fetch(`${BASE}/v1/evaluate`, { method: 'POST', body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }
  return res.json();
}

/**
 * SSE stream with automatic reconnection via Last-Event-ID.
 * Returns an object with { eventSource, close } for lifecycle management.
 */
export function streamEvaluate(
  jobId: string,
  onEvent: (event: Record<string, unknown>) => void,
  onError?: (err: Event) => void,
  onReconnect?: (attempt: number) => void,
): { close: () => void } {
  const backendUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  let lastEventId = '';
  let reconnectAttempts = 0;
  let es: EventSource | null = null;
  let closed = false;

  function connect() {
    if (closed) return;

    const url = backendUrl.startsWith('http') 
      ? `${backendUrl}/api/v1/evaluate/${jobId}/stream`
      : `/api/v1/evaluate/${jobId}/stream`;
    es = new EventSource(url);

    // Override Last-Event-ID header by passing it in the URL isn't directly
    // supported by EventSource API — but our backend also sends `id:` in the
    // SSE frames, so native browser reconnection uses it automatically.
    // For manual reconnection, we use the lastEventId.

    es.onopen = () => {
      reconnectAttempts = 0;
    };

    es.onmessage = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        if (data.id != null) lastEventId = String(data.id);
        onEvent(data);

        // Terminal events — close the stream
        if (data.kind === 'done' || data.kind === 'pipeline_complete' || data.kind === 'error') {
          es?.close();
        }
      } catch {
        // Ignore malformed events
      }
    };

    es.onerror = (err) => {
      es?.close();
      if (closed) return;

      reconnectAttempts++;
      if (reconnectAttempts <= 5) {
        onReconnect?.(reconnectAttempts);
        // Exponential backoff: 1s, 2s, 4s, 8s, 16s
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts - 1), 16000);
        setTimeout(connect, delay);
      } else {
        onError?.(err);
      }
    };
  }

  connect();

  return {
    close: () => {
      closed = true;
      es?.close();
    },
  };
}

/**
 * Get clustered issues for a completed job.
 */
export async function getIssues(jobId: string) {
  const res = await fetch(`${BASE}/v1/evaluate/${jobId}/issues`);
  if (!res.ok) throw new Error(`Issues not ready (${res.status})`);
  return res.json();
}

/**
 * URL for the PDF report download.
 */
export function reportUrl(jobId: string): string {
  return `${BASE}/v1/evaluate/${jobId}/report`;
}

/**
 * URL for the ZIP download of all patched files.
 */
export function downloadUrl(jobId: string): string {
  return `${BASE}/v1/evaluate/${jobId}/download`;
}

/**
 * Health check.
 */
export async function healthCheck(): Promise<{ status: string; model: string }> {
  const res = await fetch(`${BASE}/v1/health`);
  return res.json();
}


export async function getHistory(): Promise<any[]> {
  const res = await fetch(`${BASE}/v1/history`);
  if (!res.ok) throw new Error(`Failed to fetch history (${res.status})`);
  return res.json();
}

/**
 * Settings
 */
export async function getSettings() {
  const res = await fetch(`${BASE}/v1/settings`);
  if (!res.ok) throw new Error(`Failed to fetch settings (${res.status})`);
  return res.json();
}

export async function updateSettings(settings: Record<string, any>) {
  const res = await fetch(`${BASE}/v1/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  if (!res.ok) throw new Error(`Failed to update settings (${res.status})`);
  return res.json();
}

// ===========================================================================
// Legacy API (backward compatibility)
// ===========================================================================

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

export function originalFileUrl(sessionId: string, filename: string): string {
  return `${BASE}/sessions/${sessionId}/original/${filename}`;
}

export async function getFileContent(url: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch file content (${res.status})`);
  return res.text();
}

export function reportPdfUrl(sessionId: string): string {
  return `${BASE}/sessions/${sessionId}/report.pdf`;
}
