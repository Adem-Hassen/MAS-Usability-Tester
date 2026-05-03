'use client';

import React, { useState } from 'react';
import { usePipeline } from '@/hooks/usePipeline';
import { Card, Badge, SectionLabel } from '@/components/ui';
import { Monitor, User, MousePointer2, Clock, ChevronLeft, ChevronRight } from 'lucide-react';
import clsx from 'clsx';

export function LivePreviewPanel() {
  const { state } = usePipeline();
  const { livePreviews } = state;
  const personaIds = Object.keys(livePreviews);
  
  if (personaIds.length === 0) {
    return (
      <Card variant="base" className="h-[400px] flex flex-col items-center justify-center text-nexus-outline border-dashed">
        <Monitor size={48} className="mb-4 opacity-20" />
        <p className="text-xs font-mono uppercase tracking-widest">Awaiting Simulation Start...</p>
        <p className="text-[10px] mt-2 opacity-50 text-center max-w-[200px]">
          Live persona previews will appear here once the simulation phase begins.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 bg-nexus-primary/10 border border-nexus-primary/20 flex items-center justify-center text-nexus-primary">
            <Monitor size={12} />
          </div>
          <div>
            <h3 className="text-[11px] font-syne font-bold uppercase tracking-tight">Multi-Agent Simulation</h3>
            <div className="flex items-center gap-2 text-[9px] text-nexus-outline font-mono">
              <span className="text-nexus-secondary">LIVE PREVIEW</span>
              <span>•</span>
              <span>{personaIds.length} ACTIVE PERSONAS</span>
            </div>
          </div>
        </div>
      </div>

      <div className={clsx(
        "grid gap-4 transition-all duration-500",
        personaIds.length === 1 ? "grid-cols-1" : 
        personaIds.length === 2 ? "grid-cols-2" : 
        "grid-cols-2 xl:grid-cols-3"
      )}>
        {personaIds.map((id) => (
          <PersonaCard key={id} preview={livePreviews[id]} />
        ))}
      </div>
    </div>
  );
}

function PersonaCard({ preview }: { preview: any }) {
  return (
    <Card variant="elevated" className="p-0 overflow-hidden bg-black border-nexus-outline-variant/30 relative group shadow-xl flex flex-col h-full">
      {/* Header Info */}
      <div className="p-2 border-b border-white/5 flex items-center justify-between bg-nexus-surface/40 backdrop-blur-sm">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-2 h-2 rounded-full bg-nexus-secondary animate-pulse" />
          <span className="text-[10px] font-bold tracking-wider truncate uppercase">{preview.name.split(' ')[0]}</span>
        </div>
        <div className="flex items-center gap-1 text-[8px] font-mono text-nexus-outline">
          <Clock size={8} />
          {new Date(preview.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </div>
      </div>

      <div className="relative flex-1 bg-[#050505] min-h-[160px] flex items-center justify-center overflow-hidden">
        {/* Overlay Action */}
        {preview.action && (
          <div className="absolute top-2 left-2 z-10 animate-in fade-in slide-in-from-top-1">
            <div className="bg-black/80 backdrop-blur-md border border-nexus-primary/20 p-1.5 rounded-none max-w-[180px]">
              <div className="flex items-center gap-1 mb-0.5">
                <MousePointer2 size={8} className="text-nexus-primary" />
                <span className="text-[7px] font-bold uppercase tracking-widest text-nexus-outline/80">Active Task</span>
              </div>
              <div className="text-[9px] font-mono leading-tight break-all">
                <span className="text-nexus-primary font-bold">{preview.action}</span>
                {preview.selector && (
                  <span className="text-nexus-outline/60"> @ </span>
                )}
                <span className="text-white/80">{preview.selector}</span>
              </div>
            </div>
          </div>
        )}

        {/* Screenshot */}
        {preview.screenshot ? (
          <img 
            src={preview.screenshot.startsWith('/api') 
              ? preview.screenshot 
              : `data:image/jpeg;base64,${preview.screenshot}`
            } 
            alt={`Live preview for ${preview.name}`}
            className="w-full h-full object-contain transition-transform duration-700 group-hover:scale-[1.02]"
          />
        ) : (
          <div className="flex flex-col items-center opacity-10">
            <Monitor size={32} className="mb-2" />
            <span className="text-[8px] font-mono uppercase tracking-[0.2em]">Initialising Agent...</span>
          </div>
        )}
      </div>
    </Card>
  );
}
