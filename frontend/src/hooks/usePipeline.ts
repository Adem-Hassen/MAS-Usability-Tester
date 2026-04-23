'use client';

// src/hooks/usePipeline.ts
// Central state machine for the evaluation flow.
// Manages upload → SSE stream → results.
// Supports both V1 (/api/v1/evaluate) and legacy (/api/sessions) endpoints.

import { useCallback, useRef, useState } from 'react';
import { evaluate, streamEvaluate, getResults, getIssues } from '@/lib/api';
import type {
  SessionStatus, ConnectionStatus, StreamEvent,
  PipelineStep, Issue, Patch, SessionResults,
} from '@/types';

const PIPELINE_STEPS: { id: string; label: string }[] = [
  { id: 'supervisor',    label: 'UI Analysis'          },
  { id: 'personas',      label: 'Persona Simulations'  },
  { id: 'clustering',    label: 'Issue Clustering'     },
  { id: 'recommender',   label: 'Patch Generation'     },
  { id: 'resolver',      label: 'Conflict Resolution'  },
  { id: 'applicator',    label: 'Applying Fixes'       },
  { id: 'verification',  label: 'Verification'         },
  { id: 'report',        label: 'Report Generation'    },
  { id: 'pdf_generation', label: 'PDF Export'           },
];

export interface PipelineState {
  jobId:           string | null;
  sessionId:       string | null;  // alias for backward compat
  status:          SessionStatus;
  connection:      ConnectionStatus;
  progress:        number;
  progressLabel:   string;
  steps:           PipelineStep[];
  logs:            { level: string; message: string; ts: string }[];
  issues:          Issue[];
  patches:         Patch[];
  results:         SessionResults | null;
  error:           string | null;
  errorStage:      string | null;
  currentPage:     string | null;
  pages_done:      number;
  fileCount:       number;
  model:           string;
  reportUrl:       string;
  downloadUrl:     string;
  totalIssues:     number;
  totalPatches:    number;
}

const INIT: PipelineState = {
  jobId:           null,
  sessionId:       null,
  status:          'ready',
  connection:      'disconnected',
  progress:        0,
  progressLabel:   '',
  steps:           PIPELINE_STEPS.map(s => ({ ...s, status: 'idle' as const })),
  logs:            [],
  issues:          [],
  patches:         [],
  results:         null,
  error:           null,
  errorStage:      null,
  currentPage:     null,
  pages_done:      0,
  fileCount:       0,
  model:           '',
  reportUrl:       '',
  downloadUrl:     '',
  totalIssues:     0,
  totalPatches:    0,
};

export function usePipeline() {
  const [state, setState] = useState<PipelineState>(INIT);
  const closeRef = useRef<(() => void) | null>(null);
  const jobRef   = useRef<string | null>(null);

  const reset = useCallback(() => {
    closeRef.current?.();
    closeRef.current = null;
    jobRef.current   = null;
    setState(INIT);
  }, []);

  /**
   * V1 flow: single-step upload + start + SSE stream.
   */
  const upload = useCallback(async (files: File[]) => {
    setState(s => ({ ...s, error: null, status: 'queued' }));

    try {
      const { job_id, file_count } = await evaluate(files);
      jobRef.current = job_id;
      setState(s => ({
        ...s,
        jobId: job_id,
        sessionId: job_id,
        fileCount: file_count,
        status: 'running',
        progress: 1,
        progressLabel: 'Starting…',
        connection: 'connecting',
      }));

      // Start SSE stream
      const { close } = streamEvaluate(
        job_id,
        // onEvent
        (rawEvent) => {
          const ev = rawEvent as unknown as StreamEvent;
          setState(prev => applyEvent(prev, ev));
        },
        // onError
        () => {
          setState(s => ({
            ...s,
            connection: 'error',
            error: 'Connection to backend lost. Is the API server running?',
          }));
        },
        // onReconnect
        (attempt) => {
          setState(s => ({
            ...s,
            connection: 'reconnecting',
            progressLabel: `Reconnecting (attempt ${attempt})…`,
          }));
        },
      );

      closeRef.current = close;

      // Set connected after a small delay (let EventSource open)
      setTimeout(() => {
        setState(s => s.connection === 'connecting' ? { ...s, connection: 'connected' } : s);
      }, 500);

      return job_id;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Upload failed';
      setState(s => ({ ...s, status: 'failed', error: msg }));
      throw e;
    }
  }, []);

  const fetchResults = useCallback(async () => {
    const jid = jobRef.current;
    if (!jid) return;
    try {
      const results = await getResults(jid);
      setState(s => ({ ...s, results }));
    } catch {
      // Results not ready yet
    }
  }, []);

  // Expose `start` for backward compatibility (no-op in V1 flow since upload auto-starts)
  const start = useCallback(async (_sessionId: string) => {
    // V1 flow already started in upload()
  }, []);

  return { state, upload, start, reset, fetchResults };
}

// ── Pure event reducer ────────────────────────────────────────────────────────
function applyEvent(prev: PipelineState, ev: StreamEvent): PipelineState {
  const next = { ...prev };

  // Connection is live if we're receiving events
  if (prev.connection !== 'connected') {
    next.connection = 'connected';
  }

  switch (ev.kind) {
    // ── V1 structured events ──────────────────────────────────────────

    case 'pipeline_start':
      next.status   = 'running';
      next.model    = ev.model ?? '';
      next.progress = 2;
      next.progressLabel = `Initialising pipeline (${ev.file_count ?? 0} files)`;
      next.steps = prev.steps.map(s =>
        s.id === 'supervisor' ? { ...s, status: 'running' } : s
      );
      break;

    case 'supervisor_analysis':
      next.steps = prev.steps.map(s =>
        s.id === 'supervisor' ? { ...s, status: 'done' } : s
      );
      next.progressLabel = ev.summary ?? 'UI analysis complete';
      if (!next.progress || next.progress < 12) next.progress = 12;
      break;

    case 'persona_start':
      next.steps = prev.steps.map(s =>
        s.id === 'personas' ? { ...s, status: 'running' } : s
      );
      next.progressLabel = `Persona: ${ev.persona_name ?? ev.persona_id ?? 'unknown'}`;
      next.logs = [
        ...prev.logs,
        { level: 'info', message: `Persona started: ${ev.persona_name ?? ev.persona_id}`, ts: ev.ts },
      ].slice(-300);
      break;

    case 'persona_action':
      next.logs = [
        ...prev.logs,
        { level: 'info', message: `${ev.action_type}: ${ev.selector ?? ''} → ${ev.result ?? ''}`, ts: ev.ts },
      ].slice(-300);
      break;

    case 'persona_complete':
      next.logs = [
        ...prev.logs,
        { level: 'info', message: `Persona complete: ${ev.persona_id} (${ev.issues_found ?? 0} issues)`, ts: ev.ts },
      ].slice(-300);
      break;

    case 'clustering_start':
      next.steps = prev.steps.map(s =>
        s.id === 'personas' ? { ...s, status: 'done' } :
        s.id === 'clustering' ? { ...s, status: 'running' } : s
      );
      next.progressLabel = `Clustering ${ev.raw_issue_count ?? 0} issues…`;
      break;

    case 'clustering_complete':
      next.steps = prev.steps.map(s =>
        s.id === 'clustering' ? { ...s, status: 'done' } : s
      );
      next.progressLabel = `${ev.cluster_count ?? 0} clusters found`;
      break;

    case 'recommender_start':
      next.steps = prev.steps.map(s =>
        s.id === 'recommender' ? { ...s, status: 'running' } : s
      );
      next.progressLabel = `Recommender: ${ev.recommender_id ?? 'generating patches'}`;
      break;

    case 'recommender_patch':
      next.patches = [
        ...prev.patches,
        {
          patch_id: `rp_${Date.now()}`,
          target: ev.component ?? '',
          description: `${ev.patch_type ?? 'patch'}: ${ev.before_snippet ?? ''} → ${ev.after_snippet ?? ''}`,
          patch_type: ev.patch_type ?? '',
          page: '',
        },
      ];
      break;

    case 'conflict_detected':
      next.steps = prev.steps.map(s =>
        s.id === 'resolver' ? { ...s, status: 'running' } : s
      );
      next.progressLabel = `Conflict: ${(ev.components_affected ?? []).join(', ')}`;
      break;

    case 'conflict_resolved':
      next.steps = prev.steps.map(s =>
        s.id === 'resolver' ? { ...s, status: 'done' } : s
      );
      next.progressLabel = `Resolved via ${ev.resolution_strategy ?? 'unknown'}`;
      break;

    case 'patch_applied':
      next.steps = prev.steps.map(s =>
        s.id === 'applicator' ? { ...s, status: 'done' } : s
      );
      next.progressLabel = `Applied ${ev.patch_count ?? 0} patches to ${ev.file_name ?? ''}`;
      break;

    case 'pipeline_complete':
      next.status       = 'done';
      next.progress     = 100;
      next.totalIssues  = ev.issues_found ?? 0;
      next.totalPatches = ev.patches_applied ?? 0;
      next.reportUrl    = ev.report_url ?? '';
      next.downloadUrl  = ev.download_url ?? '';
      next.progressLabel = 'Complete';
      next.steps = prev.steps.map(s => ({ ...s, status: 'done' as const }));
      // Fetch full results after pipeline completes
      const jid = next.jobId;
      if (jid) {
        setTimeout(() => {
          getResults(jid)
            .then(results => {
              // This won't update state from inside applyEvent,
              // but the fetchResults call in the component will handle it.
            })
            .catch(() => {});
        }, 300);
      }
      break;

    // ── Legacy events ─────────────────────────────────────────────────

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
      next.totalIssues = next.issues.length;
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
      next.totalPatches = next.patches.length;
      break;

    case 'done':
      next.status   = 'done';
      next.progress = 100;
      break;

    case 'error':
      next.status     = 'failed';
      next.error      = ev.message ?? 'Unknown pipeline error';
      next.errorStage = ev.stage ?? null;
      break;
  }

  return next;
}
