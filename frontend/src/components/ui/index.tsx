'use client';

// src/components/ui/index.tsx
// Lightweight design-system primitives aligned to the Nexus token system.

import clsx from 'clsx';
import React from 'react';

// ── Card ──────────────────────────────────────────────────────────────────────
export function Card({
  children, className, noPad = false
}: { children: React.ReactNode; className?: string; noPad?: boolean }) {
  return (
    <div
      className={clsx('rounded-xl border', !noPad && 'p-5', className)}
      style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  children, className
}: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={clsx('px-5 py-3 border-b flex items-center gap-3', className)}
      style={{ borderColor: 'var(--border)' }}
    >
      {children}
    </div>
  );
}

export function CardBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={clsx('p-5', className)}>{children}</div>;
}

// ── Badge ─────────────────────────────────────────────────────────────────────
type BadgeVariant = 'amber' | 'teal' | 'danger' | 'ok' | 'neutral' | 'info';

const BADGE_MAP: Record<BadgeVariant, string> = {
  amber:   'bg-amber-950/60 text-amber-400 border-amber-800/40',
  teal:    'bg-teal-950/60  text-teal-400  border-teal-800/40',
  danger:  'bg-red-950/60   text-red-400   border-red-800/40',
  ok:      'bg-emerald-950/60 text-emerald-400 border-emerald-800/40',
  neutral: 'bg-zinc-800/60  text-zinc-400  border-zinc-700/40',
  info:    'bg-blue-950/60  text-blue-400  border-blue-800/40',
};

export function Badge({
  children, variant = 'neutral', className
}: { children: React.ReactNode; variant?: BadgeVariant; className?: string }) {
  return (
    <span className={clsx(
      'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border uppercase tracking-wide',
      BADGE_MAP[variant], className
    )}>
      {children}
    </span>
  );
}

// ── Button ────────────────────────────────────────────────────────────────────
type ButtonVariant = 'primary' | 'ghost' | 'danger';

const BTN_MAP: Record<ButtonVariant, string> = {
  primary: 'bg-amber-500/15 text-amber-300 border-amber-500/30 hover:bg-amber-500/25 hover:border-amber-400/50',
  ghost:   'bg-transparent text-zinc-400 border-zinc-700 hover:text-zinc-200 hover:border-zinc-600',
  danger:  'bg-red-950/40 text-red-400 border-red-800/40 hover:bg-red-950/60',
};

export function Button({
  children, variant = 'ghost', onClick, disabled, className, href, download, target
}: {
  children: React.ReactNode;
  variant?: ButtonVariant;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
  href?: string;
  download?: boolean | string;
  target?: string;
}) {
  const cls = clsx(
    'inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-all',
    BTN_MAP[variant],
    disabled && 'opacity-40 cursor-not-allowed pointer-events-none',
    className
  );

  if (href) {
    return (
      <a href={href} download={download} target={target} className={cls}>
        {children}
      </a>
    );
  }

  return (
    <button onClick={onClick} disabled={disabled} className={cls}>
      {children}
    </button>
  );
}

// ── Spinner ───────────────────────────────────────────────────────────────────
export function Spinner({ size = 16, color = 'var(--amber)' }: { size?: number; color?: string }) {
  return (
    <span
      className="inline-block rounded-full border-2 animate-spin flex-shrink-0"
      style={{
        width: size, height: size,
        borderColor: `${color}30`,
        borderTopColor: color,
      }}
    />
  );
}

// ── EmptyState ────────────────────────────────────────────────────────────────
export function EmptyState({
  icon, title, description
}: { icon: string; title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="text-4xl mb-4">{icon}</div>
      <p className="text-sm font-medium mb-1" style={{ color: 'var(--text2)' }}>{title}</p>
      {description && (
        <p className="text-xs max-w-xs" style={{ color: 'var(--text3)' }}>{description}</p>
      )}
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
export function Tabs({
  tabs, active, onChange
}: {
  tabs: { id: string; label: string; count?: number }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex gap-1 rounded-lg p-1" style={{ background: 'var(--surface)' }}>
      {tabs.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={clsx(
            'flex-1 py-1.5 px-3 rounded-md text-sm font-medium transition-all',
            active === tab.id ? 'text-amber-300 bg-amber-400/10' : 'text-zinc-500 hover:text-zinc-300'
          )}
        >
          {tab.label}
          {tab.count != null && tab.count > 0 && (
            <span className="ml-1.5 text-xs px-1.5 py-0.5 rounded-full bg-zinc-700 text-zinc-300">
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

// ── SectionLabel ──────────────────────────────────────────────────────────────
export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-mono font-semibold uppercase tracking-widest mb-3"
         style={{ color: 'var(--text3)' }}>
      {children}
    </div>
  );
}

// ── Severity badge ────────────────────────────────────────────────────────────
import type { Severity } from '@/types';

const SEV_VARIANT: Record<Severity, BadgeVariant> = {
  critical: 'danger',
  high:     'amber',
  medium:   'info',
  low:      'neutral',
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge variant={SEV_VARIANT[severity]}>{severity}</Badge>;
}
