'use client';

import React, { useEffect, useRef } from 'react';
import { SectionLabel, Card, StatusDot } from '@/components/ui';
import { Terminal, User, Bot, Command, CheckCircle, AlertCircle } from 'lucide-react';
import clsx from 'clsx';

interface Log {
  level: string;
  message: string;
  ts: string;
}

interface AgentStreamProps {
  logs: Log[];
  isRunning: boolean;
  activeAgents: string[];
}

export default function AgentStream({ logs, isRunning, activeAgents }: AgentStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  
  // Use provided agents or default if none (for initial look)
  const displayAgents = activeAgents.length > 0 ? activeAgents : ['Alex (Lead)'];

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-nexus-bg">
      <div className="flex items-center justify-between px-6 py-4 border-b border-nexus-outline-variant bg-[#0E0F11]">
        <div className="flex items-center gap-3">
          <Terminal size={18} className="text-nexus-primary" />
          <SectionLabel className="mb-0">Agent Simulation Stream</SectionLabel>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 bg-nexus-secondary rounded-none" />
            <span className="text-[10px] font-bold uppercase tracking-widest text-nexus-outline">Active Agents: {displayAgents.length}</span>
          </div>
          {isRunning && (
            <div className="flex items-center gap-2">
              <div className="status-pulse" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-nexus-primary">Streaming</span>
            </div>
          )}
        </div>
      </div>

      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-6 font-mono text-[12px] space-y-2 selection:bg-nexus-primary/20"
      >
        {logs.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-nexus-outline gap-3 opacity-50">
            <Bot size={48} strokeWidth={1} />
            <p className="font-sans uppercase tracking-[0.2em] text-[10px] font-bold">Waiting for agent activity...</p>
          </div>
        ) : (
          logs.map((log, i) => {
            const isPersonaStart = log.message.includes('Persona started');
            const isAction = log.message.includes(': ');
            const isError = log.level === 'error' || log.message.toLowerCase().includes('failed');

            if (isPersonaStart) {
              const personaName = log.message.split(': ')[1];
              return (
                <div key={i} className="py-4 my-2 border-y border-nexus-outline-variant/30 bg-nexus-primary/5 flex items-center gap-4 px-4">
                  <div className="w-10 h-10 bg-nexus-surface border border-nexus-outline-variant flex items-center justify-center text-nexus-primary">
                    <User size={20} />
                  </div>
                  <div>
                    <div className="text-nexus-primary font-bold uppercase tracking-widest text-[10px]">Session Initialized</div>
                    <div className="text-sm font-syne font-bold">{personaName}</div>
                  </div>
                </div>
              );
            }

            return (
              <div key={i} className={clsx(
                "group flex gap-3 transition-colors hover:bg-white/5 px-2 py-0.5",
                isError ? "text-nexus-error" : "text-white/70"
              )}>
                <span className="text-nexus-outline/40 shrink-0 select-none">[{log.ts?.split('T')[1]?.split('.')[0] || '...'}]</span>
                <span className={clsx(
                  "shrink-0 font-bold px-1 rounded-none",
                  log.level === 'error' ? "bg-nexus-error text-nexus-bg" : 
                  log.level === 'warning' ? "bg-nexus-tertiary text-nexus-bg" : "text-nexus-primary"
                )}>
                  {(log.level || 'info').toUpperCase()}
                </span>
                <span className="flex-1 break-words">
                  {log.message}
                </span>
              </div>
            );
          })
        )}
      </div>

      {/* Persona Action Monitor (Bottom Overlay) */}
      <div className="p-6 bg-gradient-to-t from-nexus-bg to-transparent pointer-events-none">
        <div className="grid grid-cols-3 gap-4 pointer-events-auto">
          {displayAgents.map((name, i) => (
            <Card key={i} variant="elevated" className="!p-3 border-l-2 border-l-nexus-primary flex items-center gap-3 bg-nexus-surface/80 backdrop-blur-sm">
              <div className="w-8 h-8 rounded-none bg-nexus-surface border border-nexus-outline-variant flex items-center justify-center">
                <User size={14} className={i === 0 ? "text-nexus-primary" : "text-nexus-outline"} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[9px] font-bold uppercase text-nexus-outline truncate">{name}</div>
                <div className="text-[10px] font-mono text-nexus-secondary flex items-center gap-1">
                  <Command size={10} />
                  <span>Scanning DOM...</span>
                </div>
              </div>
              {isRunning && i === 0 && <StatusDot status="running" className="!w-1.5 !h-1.5" />}
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
