'use client';

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { usePipeline } from '@/hooks/usePipeline';
import { Card, Badge, SectionLabel } from '@/components/ui';
import {
  Monitor, User, MousePointer2, Clock, ChevronLeft, ChevronRight,
  Maximize2, Minimize2, Search, Type, Eye, MoveVertical, Navigation
} from 'lucide-react';
import clsx from 'clsx';

/* ── Persona color palette (deterministic) ───────────────────────────── */

const PERSONA_COLORS = [
  { name: 'cyan',    bg: 'bg-cyan-500',    border: 'border-cyan-400',    text: 'text-cyan-300',    glow: 'shadow-cyan-500/50',    ring: 'ring-cyan-400/40' },
  { name: 'emerald', bg: 'bg-emerald-500', border: 'border-emerald-400', text: 'text-emerald-300', glow: 'shadow-emerald-500/50', ring: 'ring-emerald-400/40' },
  { name: 'amber',   bg: 'bg-amber-500',   border: 'border-amber-400',   text: 'text-amber-300',   glow: 'shadow-amber-500/50',   ring: 'ring-amber-400/40' },
  { name: 'rose',    bg: 'bg-rose-500',    border: 'border-rose-400',    text: 'text-rose-300',    glow: 'shadow-rose-500/50',    ring: 'ring-rose-400/40' },
  { name: 'violet',  bg: 'bg-violet-500',  border: 'border-violet-400',  text: 'text-violet-300',  glow: 'shadow-violet-500/50',  ring: 'ring-violet-400/40' },
  { name: 'orange',  bg: 'bg-orange-500',  border: 'border-orange-400',  text: 'text-orange-300',  glow: 'shadow-orange-500/50',  ring: 'ring-orange-400/40' },
  { name: 'sky',     bg: 'bg-sky-500',     border: 'border-sky-400',     text: 'text-sky-300',     glow: 'shadow-sky-500/50',     ring: 'ring-sky-400/40' },
  { name: 'lime',    bg: 'bg-lime-500',    border: 'border-lime-400',    text: 'text-lime-300',    glow: 'shadow-lime-500/50',    ring: 'ring-lime-400/40' },
];

function getPersonaColor(personaId: string) {
  let hash = 0;
  for (let i = 0; i < personaId.length; i++) {
    hash = personaId.charCodeAt(i) + ((hash << 5) - hash);
  }
  return PERSONA_COLORS[Math.abs(hash) % PERSONA_COLORS.length];
}

/* ── Action icon map ─────────────────────────────────────────────────── */

const ACTION_ICONS: Record<string, React.ReactNode> = {
  click:     <MousePointer2 size={10} />,
  type:      <Type size={10} />,
  hover:     <Eye size={10} />,
  observe:   <Eye size={10} />,
  scroll:    <MoveVertical size={10} />,
  navigate:  <Navigation size={10} />,
};

/* ── Viewport size constants (Playwright default) ────────────────────── */
const DEFAULT_VIEWPORT_W = 1280;
const DEFAULT_VIEWPORT_H = 720;

/* ── Bounding-box overlay component ──────────────────────────────────── */

function ActionOverlay({
  bbox,
  color,
  action,
  success,
  viewportWidth,
  viewportHeight,
}: {
  bbox: { x: number; y: number; width: number; height: number };
  color: typeof PERSONA_COLORS[0];
  action: string;
  success: boolean;
  viewportWidth: number;
  viewportHeight: number;
}) {
  // Scale bbox to the rendered image size
  const leftPct = (bbox.x / viewportWidth) * 100;
  const topPct = (bbox.y / viewportHeight) * 100;
  const widthPct = (bbox.width / viewportWidth) * 100;
  const heightPct = (bbox.height / viewportHeight) * 100;

  const isClick = action === 'click';

  return (
    <div
      className={clsx(
        'absolute pointer-events-none z-20',
        color.border,
        isClick ? 'animate-pulse' : ''
      )}
      style={{
        left: `${leftPct}%`,
        top: `${topPct}%`,
        width: `${widthPct}%`,
        height: `${heightPct}%`,
        boxShadow: `0 0 0 2px currentColor, 0 0 20px 4px var(--tw-shadow-color)`,
      }}
    >
      {/* Glow background */}
      <div className={clsx('absolute inset-0 opacity-20', color.bg)} />

      {/* Action badge — positioned inside box top edge to avoid clipping */}
      <div
        className={clsx(
          'absolute top-0 left-0 flex items-center gap-1 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider whitespace-nowrap z-30',
          'bg-black/90 backdrop-blur-sm border-b border-r rounded-br-sm',
          color.border,
          color.text
        )}
      >
        {ACTION_ICONS[action] || <MousePointer2 size={10} />}
        <span>{action}</span>
        {!success && <span className="text-red-400 ml-0.5">!</span>}
      </div>

      {/* Click ripple effect */}
      {isClick && (
        <div
          className={clsx(
            'absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full',
            color.bg,
            'animate-ping opacity-40'
          )}
          style={{ width: '150%', height: '150%' }}
        />
      )}

      {/* Corner markers */}
      <div className={clsx('absolute -top-0.5 -left-0.5 w-2 h-2 border-t-2 border-l-2', color.border)} />
      <div className={clsx('absolute -top-0.5 -right-0.5 w-2 h-2 border-t-2 border-r-2', color.border)} />
      <div className={clsx('absolute -bottom-0.5 -left-0.5 w-2 h-2 border-b-2 border-l-2', color.border)} />
      <div className={clsx('absolute -bottom-0.5 -right-0.5 w-2 h-2 border-b-2 border-r-2', color.border)} />
    </div>
  );
}

/* ── Persona card with overlay ───────────────────────────────────────── */

function PersonaCard({
  preview,
  personaId,
  layout,
}: {
  preview: any;
  personaId: string;
  layout: 'grid' | 'focus';
}) {
  const color = useMemo(() => getPersonaColor(personaId), [personaId]);
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgSize, setImgSize] = useState({ w: 1280, h: 720 });

  // Default viewport size for screenshots — updated when image loads
  const onImgLoad = useCallback(() => {
    if (imgRef.current) {
      setImgSize({ w: imgRef.current.naturalWidth, h: imgRef.current.naturalHeight });
    }
  }, []);

  // If no bbox but we have a selector, show a generic indicator
  const hasOverlay = preview.boundingBox && preview.boundingBox.width > 0;

  return (
    <Card
      variant="elevated"
      className={clsx(
        'p-0 overflow-hidden bg-black border-white/5 relative group shadow-2xl flex flex-col transition-all duration-300',
        layout === 'focus' ? 'aspect-video' : 'h-fit'
      )}
    >
      {/* Card Header */}
      <div className="p-1.5 px-3 border-b border-white/5 flex items-center justify-between bg-[#0d1117]/80 backdrop-blur-md z-10">
        <div className="flex items-center gap-2 min-w-0">
          <div className={clsx('w-2 h-2 rounded-full animate-pulse shadow-[0_0_8px]', color.glow, color.bg)} />
          <span className="text-[9px] font-bold tracking-widest truncate uppercase text-white/90">
            {preview.name.split(' ')[0]}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[8px] font-mono text-white/40">
          <Clock size={8} />
          {new Date(preview.ts).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </div>
      </div>

      {/* Screenshot Viewport with overlays */}
      <div className="relative flex-1 bg-[#030303] flex items-center justify-center overflow-hidden min-h-[140px]">
        {/* Action HUD Overlay (bottom gradient) — always visible, no hover dependency */}
        {preview.action && (
          <div className="absolute inset-x-0 bottom-0 pointer-events-none z-30 p-2 pb-2.5 bg-gradient-to-t from-black/90 via-black/40 to-transparent">
            <div className="bg-black/70 backdrop-blur-sm border border-white/10 p-2 rounded-sm">
              <div className="flex items-center gap-1.5 mb-1">
                <div className={clsx('w-1.5 h-1.5 rounded-full animate-pulse', color.bg)} />
                <span className="text-[8px] font-bold uppercase tracking-[0.15em] text-white/60">Executing Action</span>
              </div>
              <div className="text-[10px] font-mono leading-relaxed">
                <span className={clsx('font-bold uppercase', color.text)}>{preview.action}</span>
                {preview.selector && (
                  <>
                    <span className="text-white/30 mx-1">→</span>
                    <span className="text-white/80 break-all">{preview.selector}</span>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Bounding box overlay */}
        {hasOverlay && (
          <ActionOverlay
            bbox={preview.boundingBox}
            color={color}
            action={preview.action || 'action'}
            success={true}
            viewportWidth={imgSize.w}
            viewportHeight={imgSize.h}
          />
        )}

        {/* Screenshot image */}
        <div className="w-full h-full p-1">
          {preview.screenshot ? (
            <img
              ref={imgRef}
              src={preview.screenshot.startsWith('/api')
                ? preview.screenshot
                : `data:image/jpeg;base64,${preview.screenshot}`
              }
              alt={`Agent ${preview.name} Viewport`}
              className="w-full h-full object-contain rounded-sm"
              onLoad={onImgLoad}
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

/* ── Carousel component ──────────────────────────────────────────────── */

function PersonaCarousel({ previews, activeIds }: { previews: any; activeIds: string[] }) {
  const [index, setIndex] = useState(0);
  const id = activeIds[index % activeIds.length];

  if (!id) return null;

  return (
    <div className="relative group w-full">
      <PersonaCard preview={previews[id]} personaId={id} layout="focus" />

      {activeIds.length > 1 && (
        <>
          <button
            onClick={() => setIndex(i => (i - 1 + activeIds.length) % activeIds.length)}
            className="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/60 border border-white/10 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white/10 hover:border-white/20"
          >
            <ChevronLeft size={16} />
          </button>
          <button
            onClick={() => setIndex(i => (i + 1) % activeIds.length)}
            className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/60 border border-white/10 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white/10 hover:border-white/20"
          >
            <ChevronRight size={16} />
          </button>
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-1">
            {activeIds.map((pid, i) => {
              const c = getPersonaColor(pid);
              return (
                <div
                  key={pid}
                  className={clsx(
                    'h-1 transition-all duration-300 rounded-full',
                    i === index % activeIds.length ? 'w-6' : 'w-1',
                    i === index % activeIds.length ? c.bg : 'bg-white/20'
                  )}
                />
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

/* ── Main panel ──────────────────────────────────────────────────────── */

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
      <Card variant="base" className="h-[300px] flex flex-col items-center justify-center text-white/20 border-dashed border-white/10">
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
      'flex flex-col h-full gap-3 transition-all duration-500',
      isMaximized ? 'fixed inset-0 z-50 bg-[#0a0b0d] p-4 md:p-6 ml-sidebar' : 'relative'
    )}>
      {/* Control Bar — redesigned for robust non-overlapping layout */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-3 shrink-0 bg-white/[0.02] p-2.5 border border-white/5 backdrop-blur-md rounded-sm">
        {/* Left: Title block */}
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-7 h-7 shrink-0 bg-nexus-primary/10 border border-nexus-primary/20 flex items-center justify-center text-nexus-primary">
            <Monitor size={14} />
          </div>
          <div className="min-w-0">
            <h3 className="text-[11px] font-syne font-bold uppercase tracking-wider text-white truncate">Agent Swarm Intelligence</h3>
            <div className="flex items-center gap-1.5 text-[9px] text-white/40 font-mono">
              <span className="text-nexus-secondary animate-pulse font-bold">● LIVE</span>
              <span className="opacity-30">|</span>
              <span className="text-white/60">{personaIds.length} ACTIVE</span>
            </div>
          </div>
        </div>

        {/* Right: Controls — flex-wrap ensures no overlap */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Persona legend — compact chips, hidden on small screens */}
          <div className="hidden md:flex items-center gap-1.5">
            {filteredIds.slice(0, 4).map(pid => {
              const c = getPersonaColor(pid);
              return (
                <div key={pid} className="flex items-center gap-1 px-1.5 py-0.5 bg-black/40 border border-white/5 rounded-sm">
                  <div className={clsx('w-1.5 h-1.5 rounded-full shrink-0', c.bg)} />
                  <span className="text-[8px] text-white/50 uppercase truncate max-w-[50px]">
                    {livePreviews[pid].name.split(' ')[0]}
                  </span>
                </div>
              );
            })}
            {filteredIds.length > 4 && (
              <span className="text-[8px] text-white/30 px-1">+{filteredIds.length - 4}</span>
            )}
          </div>

          {/* Search Filter */}
          <div className="relative flex items-center">
            <Search size={10} className="absolute left-2 text-white/30 pointer-events-none" />
            <input
              type="text"
              placeholder="Filter agents..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="bg-black/60 border border-white/10 text-[10px] font-mono pl-7 pr-2 py-1.5 w-32 sm:w-36 focus:outline-none focus:border-nexus-primary/40 transition-all placeholder:opacity-30 text-white rounded-sm"
            />
          </div>

          {/* Layout Toggle — unified button group */}
          <div className="flex items-center bg-black/60 border border-white/10 rounded-sm overflow-hidden">
            <button
              onClick={() => setLayout('grid')}
              className={clsx(
                'px-2.5 py-1.5 text-[10px] font-bold tracking-wider uppercase transition-all flex items-center gap-1',
                layout === 'grid'
                  ? 'bg-nexus-primary text-black'
                  : 'text-white/40 hover:text-white hover:bg-white/5'
              )}
            >
              <Monitor size={10} />
              <span className="hidden sm:inline">GRID</span>
            </button>
            <div className="w-px h-4 bg-white/10" />
            <button
              onClick={() => setLayout('carousel')}
              className={clsx(
                'px-2.5 py-1.5 text-[10px] font-bold tracking-wider uppercase transition-all flex items-center gap-1',
                layout === 'carousel'
                  ? 'bg-nexus-primary text-black'
                  : 'text-white/40 hover:text-white hover:bg-white/5'
              )}
            >
              <Eye size={10} />
              <span className="hidden sm:inline">FOCUS</span>
            </button>
          </div>

          {/* Maximize button — same height as toggle buttons */}
          <button
            onClick={() => setIsMaximized(!isMaximized)}
            className={clsx(
              'px-2.5 py-1.5 text-[10px] font-bold tracking-wider uppercase transition-all flex items-center gap-1 border rounded-sm',
              isMaximized
                ? 'bg-white/10 border-white/20 text-white'
                : 'bg-black/60 border-white/10 text-white/40 hover:text-nexus-primary hover:border-nexus-primary/40'
            )}
            title={isMaximized ? 'Exit Fullscreen' : 'Fullscreen View'}
          >
            {isMaximized ? <Minimize2 size={10} /> : <Maximize2 size={11} />}
            <span className="hidden sm:inline">{isMaximized ? 'EXIT' : ''}</span>
          </button>
        </div>
      </div>

      {/* Viewport Area */}
      <div className={clsx(
        'flex-1 overflow-y-auto scrollbar-thin min-h-0',
        layout === 'grid' ? '' : 'flex items-center justify-center'
      )}>
        {layout === 'grid' ? (
          <div className={clsx(
            'grid gap-3 transition-all duration-300',
            filteredIds.length === 1 ? 'grid-cols-1' :
            filteredIds.length === 2 ? 'grid-cols-2' :
            'grid-cols-1 sm:grid-cols-2 xl:grid-cols-3'
          )}>
            {filteredIds.map((id) => (
              <PersonaCard key={id} preview={livePreviews[id]} personaId={id} layout="grid" />
            ))}
          </div>
        ) : (
          <div className="w-full max-w-5xl">
            <PersonaCarousel previews={livePreviews} activeIds={filteredIds} />
          </div>
        )}
      </div>
    </div>
  );
}
