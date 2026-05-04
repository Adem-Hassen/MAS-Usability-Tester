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
    <div className="flex flex-col h-full bg-[#050505] font-mono text-[11px]">
      {/* Compact Terminal Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/5 bg-[#0A0A0A]">
        <div className="flex items-center gap-2">
          <Terminal size={14} className="text-nexus-primary" />
          <span className="text-[10px] font-bold uppercase tracking-[0.1em] text-nexus-outline">Simulation Stream</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2 py-0.5 bg-nexus-surface border border-white/5">
            <User size={10} className="text-nexus-outline" />
            <span className="text-[9px] font-bold text-nexus-outline">{displayAgents.length} ACTIVE</span>
          </div>
          {isRunning && (
            <div className="flex items-center gap-2 px-2 py-0.5 bg-nexus-primary/10 border border-nexus-primary/20">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-nexus-primary opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-nexus-primary"></span>
              </span>
              <span className="text-[9px] font-bold uppercase tracking-widest text-nexus-primary">Live</span>
            </div>
          )}
        </div>
      </div>

      {/* Main Terminal Output */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-1 selection:bg-nexus-primary/30 custom-scrollbar"
      >
        {logs.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-nexus-outline gap-3 opacity-30">
            <Bot size={40} strokeWidth={1} />
            <p className="uppercase tracking-[0.2em] text-[9px] font-bold italic">Waiting for signal...</p>
          </div>
        ) : (
          logs.map((log, i) => {
            const isPersonaStart = log.message.includes('Persona started');
            const isError = log.level === 'error' || log.message.toLowerCase().includes('failed');

            if (isPersonaStart) {
              const personaName = log.message.split(': ')[1];
              return (
                <div key={i} className="py-2 my-2 border-l-2 border-nexus-primary bg-nexus-primary/5 flex flex-col gap-1 px-3">
                  <div className="text-nexus-primary font-bold uppercase tracking-widest text-[8px]">New Instance Detected</div>
                  <div className="text-[12px] font-syne font-bold text-white/90">{personaName}</div>
                </div>
              );
            }

            return (
              <div key={i} className={clsx(
                "group flex gap-2 transition-colors hover:bg-white/5 py-0.5",
                isError ? "text-nexus-error/90" : "text-nexus-outline/80"
              )}>
                <span className="text-[10px] text-white/20 shrink-0 select-none">[{log.ts?.split('T')[1]?.split('.')[0] || '...'}]</span>
                <span className={clsx(
                  "shrink-0 font-bold px-1 text-[9px] min-w-[45px] text-center",
                  log.level === 'error' ? "text-nexus-error" : 
                  log.level === 'warning' ? "text-nexus-tertiary" : "text-nexus-primary/60"
                )}>
                  {(log.level || 'info').toUpperCase()}
                </span>
                <span className="flex-1 break-words font-mono text-white/90">
                  {log.message}
                </span>
              </div>
            );
          })
        )}
      </div>

      {/* Active Persona Mini-Monitors (Footer) - Now scrollable and more compact */}
      <div className="px-4 py-2 border-t border-white/5 bg-[#080808]">
        <div className="flex flex-wrap gap-2 max-h-[80px] overflow-y-auto scrollbar-none">
          {displayAgents.map((name, i) => (
            <div key={i} className="flex items-center gap-2 p-1 px-2 border border-white/5 bg-white/[0.02] min-w-[120px] max-w-[150px]">
              <div className="w-5 h-5 shrink-0 bg-black border border-white/10 flex items-center justify-center">
                <User size={10} className={i === 0 ? "text-nexus-primary" : "text-nexus-outline/40"} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[8px] font-bold uppercase text-nexus-outline truncate tracking-tight">{name}</div>
                <div className="text-[7px] font-mono text-nexus-secondary flex items-center gap-1 opacity-70">
                  <span className="w-1 h-1 rounded-full bg-nexus-secondary animate-pulse" />
                  <span className="truncate">LIVE</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
