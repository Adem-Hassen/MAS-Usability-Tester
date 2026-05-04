'use client';

// src/components/ui/index.tsx
// Nexus Design System primitives.

import clsx from 'clsx';
import React from 'react';

// ── Card ──────────────────────────────────────────────────────────────────────
export function Card({
  children, className, noPad = false, variant = 'base', ...props
}: { 
  children: React.ReactNode; 
  className?: string; 
  noPad?: boolean; 
  variant?: 'base' | 'elevated';
  onClick?: () => void;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className={clsx(
        'rounded-none border border-nexus-outline-variant transition-all duration-200',
        variant === 'base' ? 'bg-nexus-surface' : 'bg-nexus-surface-variant',
        !noPad && 'p-6',
        className
      )}
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
      className={clsx('px-6 py-4 border-b border-nexus-outline-variant flex items-center justify-between gap-3', className)}
    >
      {children}
    </div>
  );
}

export function CardBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={clsx('p-6', className)}>{children}</div>;
}

// ── Badge ─────────────────────────────────────────────────────────────────────
type BadgeVariant = 'primary' | 'secondary' | 'tertiary' | 'error' | 'neutral' | 'success';

const BADGE_MAP: Record<BadgeVariant, string> = {
  primary:   'bg-nexus-primary/10 text-nexus-primary border-nexus-primary/20',
  secondary: 'bg-nexus-secondary/10 text-nexus-secondary border-nexus-secondary/20',
  tertiary:  'bg-nexus-tertiary/10 text-nexus-tertiary border-nexus-tertiary/20',
  error:     'bg-nexus-error/10 text-nexus-error border-nexus-error/20',
  success:   'bg-nexus-secondary/10 text-nexus-secondary border-nexus-secondary/20',
  neutral:   'bg-nexus-outline/10 text-nexus-outline border-nexus-outline/20',
};

export function Badge({
  children, variant = 'neutral', className
}: { children: React.ReactNode; variant?: BadgeVariant; className?: string }) {
  return (
    <span className={clsx(
      'inline-flex items-center px-3 py-1 rounded-pill text-[10px] font-mono font-bold border uppercase tracking-wider',
      BADGE_MAP[variant], className
    )}>
      {children}
    </span>
  );
}

// ── Button ────────────────────────────────────────────────────────────────────
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

const BTN_BASE = 'inline-flex items-center justify-center gap-2 px-6 py-2 rounded-none text-sm font-semibold transition-all duration-200 ease-out disabled:opacity-40 disabled:cursor-not-allowed';

const BTN_MAP: Record<ButtonVariant, string> = {
  primary: 'bg-gradient-to-br from-nexus-primary-container to-nexus-primary text-nexus-primary-on border-none hover:-translate-y-[2px] hover:shadow-[0_0_15px_rgba(196,192,255,0.6)]',
  secondary: 'bg-transparent text-white border border-nexus-outline-variant hover:bg-nexus-surface-variant',
  ghost:   'bg-transparent text-nexus-outline hover:text-white hover:bg-nexus-surface-variant',
  danger:  'bg-nexus-error/10 text-nexus-error border border-nexus-error/20 hover:bg-nexus-error/20',
};

export function Button({
  children, variant = 'secondary', onClick, disabled, className, href, download, target
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
  const cls = clsx(BTN_BASE, BTN_MAP[variant], className);

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

// ── Status Dot ────────────────────────────────────────────────────────────────
export function StatusDot({ status = 'idle', className }: { status?: 'idle' | 'running' | 'done' | 'error', className?: string }) {
  return (
    <span className={clsx(
      'w-2 h-2 rounded-none',
      status === 'idle' && 'bg-nexus-outline-variant',
      status === 'running' && 'status-pulse',
      status === 'done' && 'bg-nexus-secondary',
      status === 'error' && 'bg-nexus-error',
      className
    )} />
  );
}

// ── Section Label ─────────────────────────────────────────────────────────────
export function SectionLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx('text-[11px] font-mono font-bold uppercase tracking-[0.15em] text-nexus-outline mb-4', className)}>
      {children}
    </div>
  );
}

// ── Metric Card ───────────────────────────────────────────────────────────────
export function MetricCard({ 
  label, value, subtext, trend, variant = 'base', isLoading = false
}: { 
  label: string; 
  value: string | number; 
  subtext?: string; 
  trend?: { value: string; type: 'positive' | 'negative' | 'neutral' };
  variant?: 'primary' | 'secondary' | 'error' | 'base';
  isLoading?: boolean;
}) {
  const accentColor = {
    primary: 'border-t-nexus-primary',
    secondary: 'border-t-nexus-secondary',
    error: 'border-t-nexus-error',
    base: 'border-t-nexus-outline-variant'
  }[variant];

  return (
    <Card className={clsx('flex flex-col gap-1 border-t-2 overflow-hidden relative', accentColor)}>
      <SectionLabel className="mb-1">{label}</SectionLabel>
      
      {isLoading ? (
        <div className="h-9 w-24 bg-nexus-surface-variant animate-pulse" />
      ) : (
        <div key={String(value)} className="text-3xl font-syne font-bold animate-in fade-in slide-in-from-bottom-1 duration-500">
          {value}
        </div>
      )}

      {(subtext || trend) && (
        <div className="flex items-center gap-2 mt-2">
          {isLoading ? (
            <div className="h-4 w-32 bg-nexus-surface-variant animate-pulse" />
          ) : (
            <>
              {trend && (
                <span className={clsx(
                  'text-[10px] font-bold px-1.5 py-0.5 rounded-none',
                  trend.type === 'positive' && 'bg-nexus-secondary/10 text-nexus-secondary',
                  trend.type === 'negative' && 'bg-nexus-error/10 text-nexus-error',
                  trend.type === 'neutral' && 'bg-nexus-outline/10 text-nexus-outline',
                )}>
                  {trend.value}
                </span>
              )}
              {subtext && <span className="text-[10px] text-nexus-outline uppercase font-bold tracking-tight">{subtext}</span>}
            </>
          )}
        </div>
      )}
    </Card>
  );
}
// ── Notification / Toast ──────────────────────────────────────────────────────
import { X, CheckCircle, AlertTriangle, Info as InfoIcon } from 'lucide-react';
import { usePipeline } from '@/hooks/usePipeline';

export function NotificationStack() {
  const { state, dismissNotification } = usePipeline();

  if (state.notifications.length === 0) return null;

  return (
    <div className="fixed top-6 right-6 z-[9999] flex flex-col gap-4 w-96 pointer-events-none">
      {state.notifications.map((n) => (
        <Toast key={n.id} notification={n} onDismiss={() => dismissNotification(n.id)} />
      ))}
    </div>
  );
}

function Toast({ notification, onDismiss }: { notification: any, onDismiss: () => void }) {
  const { type, title, message } = notification;

  const Icon = {
    success: CheckCircle,
    error: AlertTriangle,
    info: InfoIcon
  }[type as 'success' | 'error' | 'info'] || InfoIcon;

  const typeStyles = {
    success: 'border-l-nexus-secondary bg-nexus-secondary/10',
    error: 'border-l-nexus-error bg-nexus-error/10',
    info: 'border-l-nexus-primary bg-nexus-primary/10'
  }[type as 'success' | 'error' | 'info'] || 'border-l-nexus-outline bg-nexus-surface-variant';

  return (
    <div className={clsx(
      'pointer-events-auto flex items-start gap-4 p-4 border-l-4 border border-nexus-outline-variant backdrop-blur-md animate-in slide-in-from-right-full duration-300',
      typeStyles
    )}>
      <div className={clsx(
        'mt-0.5',
        type === 'success' ? 'text-nexus-secondary' : type === 'error' ? 'text-nexus-error' : 'text-nexus-primary'
      )}>
        <Icon size={18} />
      </div>
      <div className="flex-1 space-y-1">
        <div className="text-sm font-bold uppercase tracking-wider">{title}</div>
        <div className="text-xs text-nexus-outline line-clamp-2">{message}</div>
      </div>
      <button 
        onClick={onDismiss}
        className="text-nexus-outline hover:text-white transition-colors"
      >
        <X size={16} />
      </button>
    </div>
  );
}
