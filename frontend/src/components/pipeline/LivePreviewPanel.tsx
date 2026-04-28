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
  
  const [selectedIndex, setSelectedIndex] = useState(0);
  
  if (personaIds.length === 0) {
    return (
      <Card variant="base" className="h-[500px] flex flex-col items-center justify-center text-nexus-outline border-dashed">
        <Monitor size={48} className="mb-4 opacity-20" />
        <p className="text-xs font-mono uppercase tracking-widest">Awaiting Simulation Start...</p>
        <p className="text-[10px] mt-2 opacity-50 text-center max-w-[200px]">
          Live persona previews will appear here once the simulation phase begins.
        </p>
      </Card>
    );
  }

  const selectedId = personaIds[selectedIndex];
  const preview = livePreviews[selectedId];

  const next = () => setSelectedIndex((i) => (i + 1) % personaIds.length);
  const prev = () => setSelectedIndex((i) => (i - 1 + personaIds.length) % personaIds.length);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-nexus-primary/10 border border-nexus-primary/20 flex items-center justify-center text-nexus-primary">
            <Monitor size={16} />
          </div>
          <div>
            <h3 className="text-sm font-syne font-bold uppercase tracking-tight">Live Simulation</h3>
            <div className="flex items-center gap-2 text-[10px] text-nexus-outline font-mono">
              <span className="text-nexus-secondary">ACTIVE</span>
              <span>•</span>
              <span>{personaIds.length} PERSONAS</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button 
            onClick={prev}
            className="p-1.5 hover:bg-nexus-surface-variant text-nexus-outline hover:text-white transition-colors"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="text-[10px] font-mono px-2">
            {selectedIndex + 1} / {personaIds.length}
          </span>
          <button 
            onClick={next}
            className="p-1.5 hover:bg-nexus-surface-variant text-nexus-outline hover:text-white transition-colors"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      <Card variant="elevated" className="p-0 overflow-hidden bg-black border-nexus-outline-variant/50 relative group">
        {/* Overlay Info */}
        <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
          <Badge variant="primary" className="bg-black/60 backdrop-blur-md border-nexus-primary/30 flex items-center gap-2 py-1 px-3">
            <User size={12} />
            <span className="text-[10px] font-bold tracking-wider">{preview.name}</span>
          </Badge>
          
          {preview.action && (
            <div className="bg-black/60 backdrop-blur-md border border-white/10 p-2 rounded-sm max-w-[240px] animate-in fade-in slide-in-from-left-2">
              <div className="flex items-center gap-2 mb-1">
                <MousePointer2 size={10} className="text-nexus-secondary" />
                <span className="text-[9px] font-bold uppercase tracking-widest text-nexus-outline">Current Action</span>
              </div>
              <div className="text-[11px] font-mono leading-tight break-all">
                <span className="text-nexus-secondary font-bold">{preview.action}</span>
                {preview.selector && (
                  <span className="text-nexus-outline"> on </span>
                )}
                <span className="text-white">{preview.selector}</span>
              </div>
            </div>
          )}
        </div>

        {/* Timestamp */}
        <div className="absolute bottom-4 right-4 z-10 bg-black/60 backdrop-blur-md border border-white/10 px-2 py-1 rounded-sm">
          <div className="flex items-center gap-1.5 text-[9px] font-mono text-nexus-outline">
            <Clock size={10} />
            {new Date(preview.ts).toLocaleTimeString()}
          </div>
        </div>

        {/* Screenshot Viewport */}
        <div className="aspect-video w-full bg-[#1A1B1E] flex items-center justify-center overflow-hidden">
          {preview.screenshot ? (
            <img 
              src={`data:image/jpeg;base64,${preview.screenshot}`} 
              alt={`Live preview for ${preview.name}`}
              className="w-full h-full object-contain"
            />
          ) : (
            <div className="flex flex-col items-center opacity-20">
              <Monitor size={48} className="mb-2" />
              <span className="text-[10px] font-mono uppercase tracking-[0.2em]">Initializing Stream...</span>
            </div>
          )}
        </div>

        {/* Action History / Feed (Optional) */}
        <div className="absolute bottom-4 left-4 z-10 flex flex-col gap-1 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity">
           {/* Could show last 3 actions here */}
        </div>
      </Card>

      {/* Persona Selector (Thumbnails or Dots) */}
      <div className="flex flex-wrap gap-2">
        {personaIds.map((id, i) => (
          <button
            key={id}
            onClick={() => setSelectedIndex(i)}
            className={clsx(
              "px-3 py-1.5 text-[9px] font-bold uppercase tracking-widest transition-all border",
              selectedIndex === i 
                ? "bg-nexus-primary/20 border-nexus-primary text-nexus-primary" 
                : "bg-nexus-surface border-nexus-outline-variant text-nexus-outline hover:border-white/20"
            )}
          >
            {livePreviews[id].name.split(' ')[0]}
          </button>
        ))}
      </div>
    </div>
  );
}
