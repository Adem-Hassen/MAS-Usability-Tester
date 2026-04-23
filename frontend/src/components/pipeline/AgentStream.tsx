'use client';

// src/components/pipeline/AgentStream.tsx
// Center panel — live terminal-style log output with agent action cards.

import { useRef, useEffect } from 'react';
import clsx from 'clsx';
import { SectionLabel } from '@/components/ui';

export interface LogEntry {
  level: string;
  message: string;
  ts: string;
}

export interface AgentStreamProps {
  logs: LogEntry[];
  isRunning: boolean;
}

export default function AgentStream({ logs, isRunning }: AgentStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Auto-scroll only if user hasn't scrolled up
    const container = containerRef.current;
    if (container) {
      const { scrollTop, scrollHeight, clientHeight } = container;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 80;
      if (isNearBottom) {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
      }
    }
  }, [logs.length]);

  const levelIcons: Record<string, string> = {
    info:    '›',
    warning: '⚠',
    error:   '✗',
  };

  return (
    <div className="rounded-xl border flex flex-col overflow-hidden"
         style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>

      {/* Header */}
      <div className="px-4 py-2.5 border-b flex items-center justify-between"
           style={{ background: 'var(--bg3)', borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2">
          <SectionLabel>Agent Stream</SectionLabel>
          {isRunning && (
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
          )}
        </div>
        <span className="text-[10px] font-mono" style={{ color: 'var(--text3)' }}>
          {logs.length} events
        </span>
      </div>

      {/* Log stream */}
      <div ref={containerRef}
           className="overflow-y-auto flex-1 p-4 space-y-0.5 font-mono text-xs"
           style={{ maxHeight: '520px', minHeight: '200px' }}>
        {logs.length === 0 && (
          <div className="py-12 text-center" style={{ color: 'var(--text3)' }}>
            <div className="text-2xl mb-3 opacity-30">⌁</div>
            <div className="text-sm">Waiting for pipeline events…</div>
          </div>
        )}

        {logs.map((log, i) => (
          <div key={i} className="flex gap-3 items-start py-0.5 animate-fade-in group hover:bg-white/[0.02] rounded px-1 -mx-1">
            <span className="text-[10px] pt-px flex-shrink-0 tabular-nums"
                  style={{ color: 'var(--text3)' }}>
              {formatTime(log.ts)}
            </span>
            <span className={clsx(
              'w-4 text-center flex-shrink-0 pt-px',
              log.level === 'error'   ? 'text-red-500' :
              log.level === 'warning' ? 'text-amber-500' : 'text-emerald-600/60'
            )}>
              {levelIcons[log.level] ?? '›'}
            </span>
            <span className="leading-5" style={{ color: log.level === 'error' ? 'var(--danger)' : 'var(--text2)' }}>
              {log.message}
            </span>
          </div>
        ))}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return ts?.slice(11, 19) ?? '';
  }
}
