'use client';

import React, { useState } from 'react';
import { usePipeline } from '@/hooks/usePipeline';
import { Card, Badge, SectionLabel } from '@/components/ui';
import { Monitor, User, MousePointer2, Clock, ChevronLeft, ChevronRight, Maximize2, Minimize2, Search } from 'lucide-react';
import clsx from 'clsx';

export function LivePreviewPanel() {
  const { state } = usePipeline();
  const { livePreviews } = state;
  const personaIds = Object.keys(livePreviews);
  const [layout, setLayout] = useState<'grid' | 'carousel'>('grid');
  const [filter, setFilter] = useState('');
  const [isMaximized, setIsMaximized] = useState(false);
  
  const filteredIds = personaIds.filter(id => 
    livePreviews[id].name.toLowerCase().includes(filter.toLowerCase())
  );

  if (personaIds.length === 0) {
    return (
      <Card variant="base" className="h-[300px] flex flex-col items-center justify-center text-nexus-outline border-dashed">
        <Monitor size={40} className="mb-4 opacity-20" />
        <p className="text-xs font-mono uppercase tracking-widest">Awaiting Simulation Start...</p>
        <p className="text-[10px] mt-2 opacity-50 text-center max-w-[200px]">
          Live persona previews will appear here once the simulation phase begins.
        </p>
      </Card>
    );
  }

  return (
    <div className={clsx(
      "flex flex-col h-full space-y-3 transition-all duration-500",
      isMaximized ? "fixed inset-0 z-50 bg-nexus-bg p-8 ml-sidebar" : "relative"
    )}>
      {/* Control Bar */}
      <div className="flex items-center justify-between gap-4 shrink-0 bg-nexus-surface/40 p-2 border border-white/5 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-nexus-primary/10 border border-nexus-primary/20 flex items-center justify-center text-nexus-primary shadow-[0_0_15px_rgba(var(--nexus-primary-rgb),0.1)]">
            <Monitor size={16} />
          </div>
          <div>
            <h3 className="text-[11px] font-syne font-bold uppercase tracking-[0.2em] text-white">Agent Swarm Intelligence</h3>
            <div className="flex items-center gap-2 text-[9px] text-nexus-outline font-mono">
              <span className="text-nexus-secondary animate-pulse font-bold">● LIVE STREAM</span>
              <span className="opacity-30">|</span>
              <span className="text-white/60">{personaIds.length} NODES ACTIVE</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Search Filter */}
          <div className="relative hidden lg:flex items-center">
            <Search size={10} className="absolute left-2 text-nexus-outline" />
            <input 
              type="text"
              placeholder="SEARCH AGENTS..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="bg-black/60 border border-white/10 text-[9px] font-mono pl-7 pr-2 py-1.5 w-40 focus:outline-none focus:border-nexus-primary/40 transition-all uppercase placeholder:opacity-30"
            />
          </div>

          {/* Layout Toggle */}
          <div className="flex bg-black/60 border border-white/10 p-0.5 rounded-sm">
            <button 
              onClick={() => setLayout('grid')}
              className={clsx(
                "px-3 py-1.5 text-[9px] font-bold tracking-widest uppercase transition-all",
                layout === 'grid' ? "bg-nexus-primary text-black shadow-[0_0_10px_rgba(var(--nexus-primary-rgb),0.4)]" : "text-nexus-outline hover:text-white"
              )}
            >
              GRID
            </button>
            <button 
              onClick={() => setLayout('carousel')}
              className={clsx(
                "px-3 py-1.5 text-[9px] font-bold tracking-widest uppercase transition-all",
                layout === 'carousel' ? "bg-nexus-primary text-black shadow-[0_0_10px_rgba(var(--nexus-primary-rgb),0.4)]" : "text-nexus-outline hover:text-white"
              )}
            >
              FOCUS
            </button>
          </div>

          <button 
            onClick={() => setIsMaximized(!isMaximized)}
            className="p-1.5 bg-black/60 border border-white/10 text-nexus-outline hover:text-nexus-primary hover:border-nexus-primary/40 transition-all"
            title={isMaximized ? "Exit Fullscreen" : "Fullscreen View"}
          >
            {isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      {/* Viewport Area */}
      <div className={clsx(
        "flex-1 overflow-y-auto scrollbar-thin pr-1 min-h-0",
        layout === 'grid' ? "" : "flex items-center justify-center"
      )}>
        {layout === 'grid' ? (
          <div className={clsx(
            "grid gap-3 transition-all duration-300",
            filteredIds.length === 1 ? "grid-cols-1" : 
            filteredIds.length === 2 ? "grid-cols-2" : 
            "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3"
          )}>
            {filteredIds.map((id) => (
              <PersonaCard key={id} preview={livePreviews[id]} layout="grid" />
            ))}
          </div>
        ) : (
          <div className="w-full max-w-4xl">
            <PersonaCarousel previews={livePreviews} activeIds={filteredIds} />
          </div>
        )}
      </div>
    </div>
  );
}

function PersonaCarousel({ previews, activeIds }: { previews: any, activeIds: string[] }) {
  const [index, setIndex] = useState(0);
  const id = activeIds[index % activeIds.length];
  
  if (!id) return null;

  return (
    <div className="relative group">
      <PersonaCard preview={previews[id]} layout="focus" />
      
      {activeIds.length > 1 && (
        <>
          <button 
            onClick={() => setIndex(i => (i - 1 + activeIds.length) % activeIds.length)}
            className="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/60 border border-white/10 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-nexus-primary/20 hover:border-nexus-primary/40"
          >
            <ChevronLeft size={16} />
          </button>
          <button 
            onClick={() => setIndex(i => (i + 1) % activeIds.length)}
            className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/60 border border-white/10 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-nexus-primary/20 hover:border-nexus-primary/40"
          >
            <ChevronRight size={16} />
          </button>
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-1">
            {activeIds.map((_, i) => (
              <div 
                key={i} 
                className={clsx(
                  "w-1 h-1 transition-all duration-300",
                  i === index % activeIds.length ? "w-4 bg-nexus-primary" : "bg-white/20"
                )}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function PersonaCard({ preview, layout }: { preview: any, layout: 'grid' | 'focus' }) {
  return (
    <Card 
      variant="elevated" 
      className={clsx(
        "p-0 overflow-hidden bg-black border-nexus-outline-variant/30 relative group shadow-2xl flex flex-col transition-all duration-300",
        layout === 'focus' ? "aspect-video" : "h-fit"
      )}
    >
      {/* Card Header */}
      <div className="p-1.5 px-3 border-b border-white/5 flex items-center justify-between bg-nexus-surface/60 backdrop-blur-md z-10">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-1.5 h-1.5 rounded-full bg-nexus-secondary animate-pulse shadow-[0_0_8px_rgba(var(--nexus-secondary-rgb),0.5)]" />
          <span className="text-[9px] font-bold tracking-widest truncate uppercase text-white/90">{preview.name.split(' ')[0]}</span>
        </div>
        <div className="flex items-center gap-1.5 text-[8px] font-mono text-nexus-outline/80">
          <Clock size={8} />
          {new Date(preview.ts).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </div>
      </div>

      <div className="relative flex-1 bg-[#030303] flex items-center justify-center overflow-hidden min-h-[140px]">
        {/* Action HUD Overlay */}
        {preview.action && (
          <div className="absolute inset-0 pointer-events-none z-10 flex flex-col justify-end p-2 pb-3 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300">
            <div className="bg-nexus-surface/80 backdrop-blur-md border border-white/5 p-2 rounded-sm transform translate-y-2 group-hover:translate-y-0 transition-transform duration-500">
              <div className="flex items-center gap-1.5 mb-1">
                <div className="w-1 h-1 bg-nexus-primary rounded-full" />
                <span className="text-[7px] font-bold uppercase tracking-[0.2em] text-nexus-outline">Executing Action</span>
              </div>
              <div className="text-[9px] font-mono leading-relaxed">
                <span className="text-nexus-primary font-bold uppercase">{preview.action}</span>
                {preview.selector && (
                  <>
                    <span className="text-white/40 mx-1">→</span>
                    <span className="text-white/80 break-all">{preview.selector}</span>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Screenshot Viewport */}
        <div className="w-full h-full p-1">
          {preview.screenshot ? (
            <img 
              src={preview.screenshot.startsWith('/api') 
                ? preview.screenshot 
                : `data:image/jpeg;base64,${preview.screenshot}`
              } 
              alt={`Agent ${preview.name} Viewport`}
              className="w-full h-full object-contain rounded-sm"
            />
          ) : (
            <div className="flex flex-col items-center opacity-10">
              <Monitor size={32} className="mb-2" />
              <span className="text-[8px] font-mono uppercase tracking-[0.2em]">Synchronising...</span>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
