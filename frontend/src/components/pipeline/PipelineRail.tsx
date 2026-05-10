'use client';

import React from 'react';
import { SectionLabel, StatusDot } from '@/components/ui';
import { CheckCircle2, Circle, PlayCircle, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';
import type { PipelineStep } from '@/types';
import { useAnimatedNumber } from '@/hooks/useAnimatedNumber';

interface PipelineRailProps {
  steps: PipelineStep[];
  progress: number;
  progressLabel: string;
  isRunning: boolean;
  connection: string;
  model: string;
  totalIssues: number;
  totalPatches: number;
}

function CounterCard({
  label,
  value,
  colorClass,
}: {
  label: string;
  value: number;
  colorClass: string;
}) {
  const animated = useAnimatedNumber(value, 500);
  const prevRef = React.useRef(value);
  const [flash, setFlash] = React.useState(false);

  React.useEffect(() => {
    if (value !== prevRef.current) {
      setFlash(true);
      const t = setTimeout(() => setFlash(false), 400);
      prevRef.current = value;
      return () => clearTimeout(t);
    }
  }, [value]);

  return (
    <div
      className={clsx(
        'bg-nexus-surface border p-2 text-center transition-colors duration-300',
        flash ? 'border-white/30 shadow-[0_0_12px_rgba(255,255,255,0.08)]' : 'border-nexus-outline-variant'
      )}
    >
      <div className="text-[9px] font-bold uppercase text-nexus-outline mb-0.5">{label}</div>
      <div className={clsx('text-lg font-syne font-bold tabular-nums', colorClass)}>{animated}</div>
    </div>
  );
}

export default function PipelineRail({
  steps,
  progress,
  progressLabel,
  isRunning,
  connection,
  model,
  totalIssues,
  totalPatches,
}: PipelineRailProps) {
  return (
    <div className="flex flex-col gap-6 h-full border-r border-nexus-outline-variant bg-[#0E0F11] p-6 w-64">
      <div className="space-y-1">
        <SectionLabel className="mb-0">Pipeline Engine</SectionLabel>
        <div className="text-[10px] text-nexus-outline font-mono uppercase tracking-tight truncate">
          {model || 'Nexus-Evaluator-v1'}
        </div>
      </div>

      <div className="flex-1 relative space-y-8">
        {/* Connector Line */}
        <div className="absolute left-[13px] top-2 bottom-2 w-[1px] bg-nexus-outline-variant" />

        {steps.map((step, i) => {
          const isDone = step.status === 'done';
          const isActive = step.status === 'running';
          const isError = step.status === 'error';

          return (
            <div key={step.id} className="relative flex items-start gap-4">
              <div className={clsx(
                "stepper-node",
                isDone ? "bg-nexus-secondary text-nexus-bg shadow-[0_0_8px_rgba(84,219,194,0.4)]" :
                isActive ? "bg-nexus-primary text-nexus-bg shadow-[0_0_8px_rgba(196,192,255,0.6)]" :
                "bg-nexus-surface border border-nexus-outline-variant text-nexus-outline"
              )}>
                {isDone ? <CheckCircle2 size={10} /> : isActive ? <PlayCircle size={10} className="animate-pulse" /> : <Circle size={10} />}
              </div>
              <div className="flex-1 min-w-0">
                <div className={clsx(
                  "text-[11px] font-bold uppercase tracking-widest",
                  isDone ? "text-nexus-secondary" : isActive ? "text-nexus-primary" : "text-nexus-outline"
                )}>
                  {step.label}
                </div>
                {isActive && (
                  <div className="text-[10px] text-white/80 font-mono mt-1 truncate">
                    {progressLabel}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="pt-6 border-t border-nexus-outline-variant space-y-4">
        <div className="space-y-1.5">
          <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest text-nexus-outline">
            <span>Overall Progress</span>
            <span className="text-nexus-primary">{progress}%</span>
          </div>
          <div className="h-1 bg-nexus-surface-variant rounded-none overflow-hidden">
            <div 
              className="h-full bg-nexus-primary transition-all duration-500 shadow-[0_0_8px_rgba(196,192,255,0.4)]"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <CounterCard label="Issues" value={totalIssues} colorClass="text-nexus-error" />
          <CounterCard label="Patches" value={totalPatches} colorClass="text-nexus-secondary" />
        </div>

        <div className="flex items-center gap-2">
          <div className={clsx(
            "w-1.5 h-1.5 rounded-none",
            connection === 'connected' ? "bg-nexus-secondary shadow-[0_0_4px_rgba(84,219,194,0.4)]" : "bg-nexus-error"
          )} />
          <span className="text-[9px] font-bold uppercase text-nexus-outline tracking-widest">
            API Status: {connection}
          </span>
        </div>
      </div>
    </div>
  );
}
