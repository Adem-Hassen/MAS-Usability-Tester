'use client';

import React, { createContext, useContext, useCallback, useRef, useState, useEffect } from 'react';
import { evaluate, streamEvaluate, getResults, getActiveRun, getJobEvents } from '@/lib/api';
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
  sessionId:       string | null;
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
  activeAgents:    string[]; // Track spawned agents
  livePreviews:    Record<string, {
    name: string;
    action?: string;
    selector?: string;
    screenshot?: string;
    ts: string;
  }>;
  notifications: { id: string; type: 'success' | 'error' | 'info'; title: string; message: string; ts: string }[];
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
  activeAgents:    [],
  livePreviews:    {},
  notifications:   [],
};

interface PipelineContextType {
  state: PipelineState;
  upload: (files: File[]) => Promise<string>;
  reset: () => void;
  fetchResults: () => Promise<void>;
  connect: (jobId: string) => void;
  dismissNotification: (id: string) => void;
}

const PipelineContext = createContext<PipelineContextType | undefined>(undefined);

export function PipelineProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<PipelineState>(INIT);
  const closeRef = useRef<(() => void) | null>(null);
  const connectedJobId = useRef<string | null>(null);

  const reset = useCallback(() => {
    closeRef.current?.();
    closeRef.current = null;
    connectedJobId.current = null;
    setState(INIT);
  }, []);

  const connect = useCallback(async (jobId: string) => {
    if (connectedJobId.current === jobId) return;
    
    // Close existing connection if any
    closeRef.current?.();
    connectedJobId.current = jobId;

    setState(s => ({ 
      ...s, 
      jobId, 
      sessionId: jobId, 
      connection: 'connecting',
      status: s.status === 'ready' ? 'running' : s.status 
    }));

    // Step 1: Recover history if needed
    try {
      const history = await getJobEvents(jobId);
      if (history.length > 0) {
        setState(prev => {
          let next: PipelineState = { ...prev, jobId, sessionId: jobId };
          for (const ev of history) {
            next = applyEvent(next, ev as unknown as StreamEvent);
          }
          return next;
        });
      }
    } catch (e) {
      console.warn("Failed to recover history", e);
    }

    // Step 2: Stream remaining
    const { close } = streamEvaluate(
      jobId,
      (ev) => {
        setState(prev => applyEvent(prev, ev as unknown as StreamEvent));
      },
      () => {
        setState(s => ({
          ...s,
          connection: 'error',
          error: 'Connection to backend lost.',
        }));
      },
      (attempt) => {
        setState(s => ({
          ...s,
          connection: 'reconnecting',
          progressLabel: `Reconnecting (attempt ${attempt})…`,
        }));
      }
    );

    closeRef.current = close;
  }, []);

  // Auto-recovery
  useEffect(() => {
    async function check() {
      try {
        const { job_id } = await getActiveRun();
        if (job_id) {
          console.log("Found active run:", job_id);
          connect(job_id);
        }
      } catch (e) {
        console.error("Active run check failed", e);
      }
    }
    if (!state.jobId) {
      check();
    }
  }, [state.jobId, connect]);

  const dismissNotification = useCallback((id: string) => {
    setState(s => ({
      ...s,
      notifications: s.notifications.filter(n => n.id !== id)
    }));
  }, []);

  const upload = useCallback(async (files: File[]) => {
    // Clear previous state for a fresh start
    setState(s => ({ 
      ...INIT, 
      status: 'queued',
      fileCount: files.length
    }));
    
    try {
      const { job_id, file_count } = await evaluate(files);
      setState(s => ({ ...s, jobId: job_id, fileCount: file_count }));
      connect(job_id);
      return job_id;
    } catch (e: any) {
      const msg = e instanceof Error ? e.message : 'Upload failed';
      setState(s => ({ ...s, status: 'failed', error: msg }));
      throw e;
    }
  }, [connect]);

  const fetchResults = useCallback(async () => {
    if (!state.jobId) return;
    try {
      const results = await getResults(state.jobId);
      setState(s => ({ ...s, results }));
    } catch (err) {
      console.warn("Results not ready", err);
    }
  }, [state.jobId]);

  return (
    <PipelineContext.Provider value={{ state, upload, reset, fetchResults, connect, dismissNotification }}>
      {children}
    </PipelineContext.Provider>
  );
}

export function usePipeline() {
  const context = useContext(PipelineContext);
  if (!context) throw new Error('usePipeline must be used within a PipelineProvider');
  return context;
}

// ── Pure event reducer ────────────────────────────────────────────────────────
function applyEvent(prev: PipelineState, ev: StreamEvent): PipelineState {
  const next = { ...prev };

  if (prev.connection !== 'connected') {
    next.connection = 'connected';
  }

  switch (ev.kind) {
    case 'pipeline_start':
      next.status = 'running';
      next.model = ev.model ?? '';
      next.progress = 2;
      next.progressLabel = `Initialising pipeline (${ev.file_count ?? 0} files)`;
      next.steps = prev.steps.map(s => s.id === 'supervisor' ? { ...s, status: 'running' } : s);
      break;

    case 'supervisor_analysis':
      next.steps = prev.steps.map(s =>
        s.id === 'supervisor' ? { ...s, status: 'done' } : s
      );
      next.progressLabel = ev.summary ?? 'UI analysis complete';
      if (!next.progress || next.progress < 12) next.progress = 12;
      break;

    case 'persona_start':
      next.steps = prev.steps.map(s => s.id === 'personas' ? { ...s, status: 'running' } : s);
      const personaName = ev.persona_name || ev.persona_id || 'Agent';
      if (!next.activeAgents.includes(personaName)) {
        next.activeAgents = [...next.activeAgents, personaName];
      }
      
      // Live Preview Init
      if (ev.persona_id) {
        next.livePreviews = {
          ...prev.livePreviews,
          [ev.persona_id]: {
            name: personaName,
            screenshot: ev.screenshot,
            ts: ev.ts
          }
        };
      }

      next.logs = [...prev.logs, { level: 'info', message: `Persona started: ${personaName}`, ts: ev.ts }].slice(-300);
      break;

    case 'persona_action':
      // Live Preview Update
      if (ev.persona_id) {
        next.livePreviews = {
          ...prev.livePreviews,
          [ev.persona_id]: {
            ...(prev.livePreviews[ev.persona_id] || { name: ev.persona_name || 'Agent' }),
            action: ev.action_type,
            selector: ev.selector,
            screenshot: ev.screenshot,
            ts: ev.ts
          }
        };
      }

      next.logs = [
        ...prev.logs,
        { level: 'info', message: `${ev.action_type}: ${ev.selector ?? ''} → ${ev.result ?? ''}`, ts: ev.ts },
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
      next.progressLabel = `Generating patch proposals…`;
      break;

    case 'recommender_patch':
      const patchMsg = ev.status === 'done' ? 'Generated patch' : 'Patch generation failed';
      next.progressLabel = patchMsg;
      if (ev.status === 'done') {
        next.totalPatches = prev.totalPatches + 1;
      }
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
      next.status = 'done';
      next.progress = 100;
      next.totalIssues = ev.issues_found ?? 0;
      next.totalPatches = ev.patches_applied ?? 0;
      next.reportUrl = ev.report_url ?? '';
      next.downloadUrl = ev.download_url ?? '';
      next.steps = prev.steps.map(s => ({ ...s, status: 'done' as const }));
      
      // Add notification
      next.notifications = [
        ...prev.notifications,
        {
          id: `done_${Date.now()}`,
          type: 'success',
          title: 'Evaluation Complete',
          message: `Found ${ev.issues_found ?? 0} issues across ${ev.file_count ?? 0} files.`,
          ts: ev.ts
        }
      ];
      break;

    case 'progress':
      next.progress = ev.value ?? prev.progress;
      next.progressLabel = ev.label ?? prev.progressLabel;
      break;

    case 'step':
      next.steps = prev.steps.map(s => s.id === ev.step ? { ...s, status: ev.status ?? 'idle', page: ev.page } : s);
      if (ev.label) next.progressLabel = ev.label;
      break;

    case 'log':
      next.logs = [...prev.logs, { level: ev.level ?? 'info', message: ev.message ?? '', ts: ev.ts }].slice(-300);
      break;

    case 'issue':
      next.issues = [...prev.issues, {
        issue_id: ev.issue_id ?? `i_${Date.now()}`,
        title: ev.title ?? '(untitled)',
        severity: ev.severity ?? 'medium',
        category: ev.category ?? 'usability',
        description: ev.description ?? '',
        page: ev.page ?? '',
      }];
      next.totalIssues = next.issues.length;
      break;

    case 'patch':
      next.patches = [...prev.patches, {
        patch_id: ev.patch_id ?? `p_${Date.now()}`,
        target: ev.target ?? '',
        description: ev.description ?? '',
        patch_type: ev.patch_type ?? '',
        page: ev.page ?? '',
      }];
      next.totalPatches = next.patches.length;
      break;

    case 'error':
      next.status = 'failed';
      next.error = ev.message ?? 'Unknown error';
      // Add notification
      next.notifications = [
        ...prev.notifications,
        {
          id: `err_${Date.now()}`,
          type: 'error',
          title: 'Evaluation Failed',
          message: ev.message ?? 'An unexpected error occurred.',
          ts: ev.ts
        }
      ];
      break;
  }

  return next;
}
