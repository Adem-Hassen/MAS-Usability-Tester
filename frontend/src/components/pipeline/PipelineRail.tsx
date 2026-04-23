'use client';

// src/components/pipeline/PipelineRail.tsx
// Left sidebar component showing pipeline stage progress.

import clsx from 'clsx';
import { Spinner, SectionLabel } from '@/components/ui';
import type { PipelineStep, ConnectionStatus } from '@/types';

function StepRow({ step }: { step: PipelineStep }) {
  const dotCls: Record<string, string> = {
    idle:    'w-2.5 h-2.5 rounded-full bg-zinc-700/50 ring-1 ring-zinc-700',
    running: 'w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse shadow-[0_0_10px_rgba(200,169,110,0.7)] ring-1 ring-amber-500/40',
    done:    'w-2.5 h-2.5 rounded-full bg-emerald-500 ring-1 ring-emerald-500/30',
    error:   'w-2.5 h-2.5 rounded-full bg-red-500 ring-1 ring-red-500/30',
  };
  const textCls: Record<string, string> = {
    idle:    'text-zinc-600',
    running: 'text-amber-300 font-medium',
    done:    'text-zinc-400',
    error:   'text-red-400',
  };
  const lineCls: Record<string, string> = {
    idle:    'bg-zinc-800',
    running: 'bg-amber-400/30',
    done:    'bg-emerald-500/30',
    error:   'bg-red-500/30',
  };

  return (
    <div className="relative flex items-center gap-3 py-2 group">
      {/* Connector line */}
      <div className="absolute left-[5px] top-0 h-full w-px -z-10"
           style={{ background: 'var(--border)' }} />

      <span className={dotCls[step.status] ?? dotCls.idle} />
      <span className={clsx('text-sm transition-colors flex-1', textCls[step.status] ?? textCls.idle)}>
        {step.label}
      </span>
      {step.status === 'running' && step.page && (
        <span className="text-[10px] font-mono text-amber-500/70 truncate max-w-[100px]">
          {step.page}
        </span>
      )}
      {step.status === 'done' && (
        <span className="text-[11px] text-emerald-600 font-medium">✓</span>
      )}
      {step.status === 'error' && (
        <span className="text-[11px] text-red-500 font-medium">✗</span>
      )}
    </div>
  );
}

export interface PipelineRailProps {
  steps:          PipelineStep[];
  progress:       number;
  progressLabel:  string;
  isRunning:      boolean;
  connection:     ConnectionStatus;
  model?:         string;
  totalIssues?:   number;
  totalPatches?:  number;
}

export default function PipelineRail({
  steps, progress, progressLabel, isRunning, connection, model, totalIssues = 0, totalPatches = 0,
}: PipelineRailProps) {
  return (
    <div className="space-y-4">
      {/* Connection status */}
      <div className="flex items-center gap-2 px-1">
        <span className={clsx(
          'w-1.5 h-1.5 rounded-full flex-shrink-0',
          connection === 'connected'    ? 'bg-emerald-500' :
          connection === 'connecting'   ? 'bg-amber-400 animate-pulse' :
          connection === 'reconnecting' ? 'bg-amber-400 animate-pulse' :
          connection === 'error'        ? 'bg-red-500' :
          'bg-zinc-600'
        )} />
        <span className="text-[10px] font-mono uppercase tracking-widest"
              style={{ color: 'var(--text3)' }}>
          {connection === 'connected'    ? 'Live' :
           connection === 'connecting'   ? 'Connecting' :
           connection === 'reconnecting' ? 'Reconnecting' :
           connection === 'error'        ? 'Disconnected' :
           'Offline'}
        </span>
        {model && (
          <span className="text-[10px] font-mono ml-auto truncate max-w-[120px]"
                style={{ color: 'var(--text3)' }}>
            {model}
          </span>
        )}
      </div>

      {/* Pipeline steps */}
      <div className="rounded-xl border p-4 animate-fade-in"
           style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>
        <SectionLabel>Pipeline</SectionLabel>
        <div className="relative">
          {steps.map(s => <StepRow key={s.id} step={s} />)}
        </div>
      </div>

      {/* Progress bar */}
      {isRunning && (
        <div className="space-y-2 animate-fade-in">
          <div className="flex justify-between text-xs font-mono"
               style={{ color: 'var(--text3)' }}>
            <span className="truncate mr-2 flex-1">{progressLabel}</span>
            <span className="font-medium" style={{ color: 'var(--amber)' }}>
              {progress}%
            </span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden"
               style={{ background: 'var(--surface)' }}>
            <div className="h-full rounded-full transition-all duration-700 ease-out"
                 style={{
                   width: `${progress}%`,
                   background: 'linear-gradient(90deg, var(--amber) 0%, var(--amber-light) 100%)',
                   boxShadow: '0 0 12px rgba(200,169,110,0.3)',
                 }} />
          </div>
        </div>
      )}

      {/* Stats */}
      {(totalIssues > 0 || totalPatches > 0) && (
        <div className="rounded-xl border p-4 grid grid-cols-2 gap-3"
             style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>
          <div className="text-center">
            <div className="font-display font-bold text-xl" style={{ color: 'var(--danger)' }}>
              {totalIssues}
            </div>
            <div className="text-[10px] font-mono" style={{ color: 'var(--text3)' }}>
              Issues
            </div>
          </div>
          <div className="text-center">
            <div className="font-display font-bold text-xl" style={{ color: 'var(--ok)' }}>
              {totalPatches}
            </div>
            <div className="text-[10px] font-mono" style={{ color: 'var(--text3)' }}>
              Patches
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
