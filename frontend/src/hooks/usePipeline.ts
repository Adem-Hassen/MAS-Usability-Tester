'use client';

// src/hooks/usePipeline.ts
// Central state machine for the evaluation flow.
// Manages upload → start → SSE stream → results.

import { useCallback, useRef, useState } from 'react';
import { createSession, runSession, streamSession, getResults } from '@/lib/api';
import type { SessionStatus, StreamEvent, PipelineStep, Issue, Patch, SessionResults } from '@/types';

const PIPELINE_STEPS: { id: string; label: string }[] = [
  { id: 'supervisor',    label: 'UI Analysis'          },
  { id: 'personas',      label: 'Persona Simulations'  },
  { id: 'clustering',    label: 'Issue Clustering'     },
  { id: 'recommender',   label: 'Patch Generation'     },
  { id: 'resolver',      label: 'Conflict Resolution'  },
  { id: 'applicator',    label: 'Applying Fixes'       },
  { id: 'verification',  label: 'Verification'         },
  { id: 'report',        label: 'Report Generation'    },
  { id: 'pdf_generation','label': 'PDF Export'         },
];

export interface PipelineState {
  sessionId:    string | null;
  status:       SessionStatus;
  progress:     number;
  progressLabel:string;
  steps:        PipelineStep[];
  logs:         { level: string; message: string; ts: string }[];
  issues:       Issue[];
  patches:      Patch[];
  results:      SessionResults | null;
  error:        string | null;
  currentPage:  string | null;
  pages_done:   number;
}

const INIT: PipelineState = {
  sessionId:    null,
  status:       'ready',
  progress:     0,
  progressLabel:'',
  steps:        PIPELINE_STEPS.map(s => ({ ...s, status: 'idle' as const })),
  logs:         [],
  issues:       [],
  patches:      [],
  results:      null,
  error:        null,
  currentPage:  null,
  pages_done:   0,
};

export function usePipeline() {
  const [state, setState] = useState<PipelineState>(INIT);
  const esRef      = useRef<EventSource | null>(null);
  const sessionRef = useRef<string | null>(null); // stable ref — avoids stale closures

  const reset = useCallback(() => {
    esRef.current?.close();
    esRef.current    = null;
    sessionRef.current = null;
    setState(INIT);
  }, []);

  const upload = useCallback(async (files: File[]): Promise<string> => {
    setState(s => ({ ...s, error: null }));
    const { session_id } = await createSession(files);
    sessionRef.current = session_id;
    setState(s => ({ ...s, sessionId: session_id }));
    return session_id;
  }, []);

  const start = useCallback(async (sessionId: string) => {
    await runSession(sessionId);
    setState(s => ({ ...s, status: 'running', progress: 1, progressLabel: 'Starting…' }));

    const es = streamSession(sessionId);
    esRef.current = es;

    es.onmessage = (e: MessageEvent) => {
      let ev: StreamEvent;
      try { ev = JSON.parse(e.data); } catch { return; }

      setState(prev => applyEvent(prev, ev));

      // When pipeline finishes, fetch full results
      if (ev.kind === 'done') {
        es.close();
        const sid = sessionRef.current;
        if (sid) {
          setTimeout(() => {
            getResults(sid)
              .then(results => setState(s => ({ ...s, results })))
              .catch(() => {});
          }, 300);
        }
      }
    };

    es.onerror = () => {
      setState(s => ({
        ...s,
        error: 'Connection to backend lost. Is the API server running on :8000?'
      }));
      es.close();
    };
  }, []);

  const fetchResults = useCallback(async () => {
    const sid = sessionRef.current;
    if (!sid) return;
    try {
      const results = await getResults(sid);
      setState(s => ({ ...s, results }));
    } catch {}
  }, []);

  return { state, upload, start, reset, fetchResults };
}

// ── Pure event reducer ────────────────────────────────────────────────────────
function applyEvent(prev: PipelineState, ev: StreamEvent): PipelineState {
  const next = { ...prev };

  switch (ev.kind) {
    case 'progress':
      next.progress      = ev.value  ?? prev.progress;
      next.progressLabel = ev.label  ?? prev.progressLabel;
      break;

    case 'step':
      next.currentPage = ev.page ?? prev.currentPage;
      if (ev.page) {
        const pages_done = ev.step === 'complete'
          ? prev.pages_done + 1
          : prev.pages_done;
        next.pages_done = pages_done;
      }
      next.steps = prev.steps.map(s =>
        s.id === ev.step
          ? { ...s, status: ev.status ?? 'idle', page: ev.page }
          : s
      );
      if (ev.label) next.progressLabel = ev.label;
      break;

    case 'log':
      next.logs = [
        ...prev.logs,
        { level: ev.level ?? 'info', message: ev.message ?? '', ts: ev.ts },
      ].slice(-300);
      break;

    case 'issue':
      next.issues = [
        ...prev.issues,
        {
          issue_id:    ev.issue_id    ?? `i_${Date.now()}`,
          title:       ev.title       ?? '(untitled)',
          severity:    ev.severity    ?? 'medium',
          category:    ev.category    ?? 'usability',
          description: ev.description ?? '',
          page:        ev.page        ?? '',
        },
      ];
      break;

    case 'patch':
      next.patches = [
        ...prev.patches,
        {
          patch_id:    ev.patch_id    ?? `p_${Date.now()}`,
          target:      ev.target      ?? '',
          description: ev.description ?? '',
          patch_type:  ev.patch_type  ?? '',
          page:        ev.page        ?? '',
        },
      ];
      break;

    case 'done':
      next.status   = 'done';
      next.progress = 100;
      break;

    case 'error':
      next.status = 'failed';
      next.error  = ev.message ?? 'Unknown pipeline error';
      break;
  }

  return next;
}
