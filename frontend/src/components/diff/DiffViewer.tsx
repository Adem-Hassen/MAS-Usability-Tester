'use client';

// src/components/diff/DiffViewer.tsx
// Renders a side-by-side or unified diff between original and fixed HTML.
// Uses the `diff` library for line-level diffing with no heavy dependencies.

import { useMemo, useState } from 'react';
import clsx from 'clsx';

interface DiffViewerProps {
  original: string;
  fixed:    string;
  filename?: string;
}

type LineKind = 'equal' | 'added' | 'removed';

interface DiffLine {
  kind:    LineKind;
  content: string;
  lineNo:  { left?: number; right?: number };
}

function computeDiff(a: string, b: string): DiffLine[] {
  const aLines = a.split('\n');
  const bLines = b.split('\n');

  // Simple LCS-based diff
  const m = aLines.length;
  const n = bLines.length;

  // Build LCS table (capped at 400 lines each for perf)
  const capM = Math.min(m, 400);
  const capN = Math.min(n, 400);
  const dp: number[][] = Array.from({ length: capM + 1 }, () =>
    new Array(capN + 1).fill(0)
  );

  for (let i = 1; i <= capM; i++) {
    for (let j = 1; j <= capN; j++) {
      dp[i][j] = aLines[i - 1] === bLines[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  const lines: DiffLine[] = [];
  let leftNo  = 1;
  let rightNo = 1;
  let i = capM, j = capN;
  const seq: Array<['eq' | 'del' | 'ins', string]> = [];

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && aLines[i - 1] === bLines[j - 1]) {
      seq.push(['eq', aLines[i - 1]]);
      i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      seq.push(['ins', bLines[j - 1]]);
      j--;
    } else {
      seq.push(['del', aLines[i - 1]]);
      i--;
    }
  }
  seq.reverse();

  for (const [kind, content] of seq) {
    if (kind === 'eq') {
      lines.push({ kind: 'equal',   content, lineNo: { left: leftNo++,  right: rightNo++ } });
    } else if (kind === 'del') {
      lines.push({ kind: 'removed', content, lineNo: { left: leftNo++ } });
    } else {
      lines.push({ kind: 'added',   content, lineNo: { right: rightNo++ } });
    }
  }

  // Append overflow lines unchanged
  if (m > capM) {
    for (let k = capM; k < m; k++) {
      lines.push({ kind: 'equal', content: aLines[k], lineNo: { left: leftNo++, right: rightNo++ } });
    }
  }

  return lines;
}

export default function DiffViewer({ original, fixed, filename }: DiffViewerProps) {
  const [mode, setMode]         = useState<'split' | 'unified'>('unified');
  const [showContext, setShowContext] = useState(true);

  const diff = useMemo(() => computeDiff(original, fixed), [original, fixed]);

  const changed = diff.filter(l => l.kind !== 'equal').length;
  const added   = diff.filter(l => l.kind === 'added').length;
  const removed = diff.filter(l => l.kind === 'removed').length;

  // In context mode, show only changed lines ± 3 context lines
  const visibleLines = useMemo(() => {
    if (!showContext) return diff;
    const changedIdx = new Set(
      diff.map((l, i) => l.kind !== 'equal' ? i : -1).filter(i => i >= 0)
    );
    const visible = new Set<number>();
    for (const idx of changedIdx) {
      for (let k = Math.max(0, idx - 3); k <= Math.min(diff.length - 1, idx + 3); k++) {
        visible.add(k);
      }
    }
    return diff.map((l, i) => ({ ...l, hidden: !visible.has(i) }));
  }, [diff, showContext]);

  const lineStyle: Record<LineKind, string> = {
    equal:   'bg-transparent text-zinc-400',
    added:   'bg-emerald-950/60 text-emerald-300 border-l-2 border-emerald-500',
    removed: 'bg-red-950/60 text-red-300 border-l-2 border-red-500 line-through opacity-70',
  };

  const linePrefix: Record<LineKind, string> = {
    equal:   ' ',
    added:   '+',
    removed: '−',
  };

  if (original === fixed) {
    return (
      <div className="rounded-xl border p-8 text-center"
           style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>
        <div className="text-2xl mb-2">✓</div>
        <p className="text-sm" style={{ color: 'var(--text2)' }}>
          No changes — file is identical to original.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border overflow-hidden"
         style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>

      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b"
           style={{ background: 'var(--bg3)', borderColor: 'var(--border)' }}>
        {filename && (
          <span className="text-xs font-mono" style={{ color: 'var(--amber)' }}>
            {filename}
          </span>
        )}

        <div className="flex items-center gap-3 text-xs font-mono ml-2">
          <span style={{ color: 'var(--ok)' }}>+{added}</span>
          <span style={{ color: 'var(--danger)' }}>−{removed}</span>
          <span style={{ color: 'var(--text3)' }}>{changed} changes</span>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setShowContext(v => !v)}
            className={clsx(
              'text-xs px-2 py-1 rounded transition-colors',
              showContext ? 'text-amber-400 bg-amber-400/10' : 'text-zinc-500 hover:text-zinc-300'
            )}
          >
            Context
          </button>
          <div className="flex rounded overflow-hidden border" style={{ borderColor: 'var(--border)' }}>
            {(['unified', 'split'] as const).map(m => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={clsx(
                  'text-xs px-2.5 py-1 capitalize transition-colors',
                  mode === m ? 'bg-amber-400/15 text-amber-400' : 'text-zinc-500 hover:text-zinc-300'
                )}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Diff content */}
      <div className="overflow-auto max-h-[520px]">
        {mode === 'unified' ? (
          <UnifiedView lines={visibleLines} lineStyle={lineStyle} linePrefix={linePrefix} />
        ) : (
          <SplitView diff={diff} showContext={showContext} />
        )}
      </div>
    </div>
  );
}

// ── Unified view ──────────────────────────────────────────────────────────────
function UnifiedView({ lines, lineStyle, linePrefix }: {
  lines: Array<DiffLine & { hidden?: boolean }>;
  lineStyle: Record<LineKind, string>;
  linePrefix: Record<LineKind, string>;
}) {
  let prevHidden = false;
  return (
    <table className="w-full border-collapse font-mono text-xs" style={{ tableLayout: 'fixed' }}>
      <tbody>
        {lines.map((line, i) => {
          const isCollapsed = line.hidden && !prevHidden;
          prevHidden = !!line.hidden;
          if (line.hidden) {
            return isCollapsed ? (
              <tr key={i}>
                <td colSpan={3} className="py-1 px-4 text-center text-[11px]"
                    style={{ color: 'var(--text3)', background: 'var(--bg3)' }}>
                  ···
                </td>
              </tr>
            ) : null;
          }
          return (
            <tr key={i} className={clsx('group', lineStyle[line.kind])}>
              <td className="w-10 text-right pr-3 select-none py-0.5"
                  style={{ color: 'var(--text3)', background: 'var(--bg3)' }}>
                {line.lineNo.left ?? ''}
              </td>
              <td className="w-10 text-right pr-3 select-none py-0.5"
                  style={{ color: 'var(--text3)', background: 'var(--bg3)' }}>
                {line.lineNo.right ?? ''}
              </td>
              <td className="w-6 text-center select-none py-0.5 font-bold" style={{ color: 'var(--text3)' }}>
                {linePrefix[line.kind]}
              </td>
              <td className="py-0.5 pr-4 whitespace-pre-wrap break-all leading-5">
                {line.content}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ── Split view ────────────────────────────────────────────────────────────────
function SplitView({ diff, showContext }: { diff: DiffLine[]; showContext: boolean }) {
  const leftLines  = diff.filter(l => l.kind !== 'added');
  const rightLines = diff.filter(l => l.kind !== 'removed');

  const leftStyle:  Record<LineKind, string> = {
    equal:   'bg-transparent text-zinc-400',
    added:   'bg-transparent text-zinc-700',
    removed: 'bg-red-950/60 text-red-300',
  };
  const rightStyle: Record<LineKind, string> = {
    equal:   'bg-transparent text-zinc-400',
    added:   'bg-emerald-950/60 text-emerald-300',
    removed: 'bg-transparent text-zinc-700',
  };

  const renderHalf = (lines: DiffLine[], style: Record<LineKind, string>, side: 'left' | 'right') => (
    <div className="flex-1 overflow-auto border-r last:border-r-0 font-mono text-xs"
         style={{ borderColor: 'var(--border)' }}>
      <div className="px-2 py-1 text-[10px] uppercase tracking-widest font-bold border-b"
           style={{ color: 'var(--text3)', borderColor: 'var(--border)', background: 'var(--bg3)' }}>
        {side === 'left' ? 'Original' : 'Fixed'}
      </div>
      {lines.map((line, i) => (
        <div key={i} className={clsx('flex py-0.5', style[line.kind])}>
          <span className="w-10 text-right pr-3 select-none flex-shrink-0"
                style={{ color: 'var(--text3)' }}>
            {side === 'left' ? line.lineNo.left : line.lineNo.right}
          </span>
          <span className="whitespace-pre-wrap break-all leading-5 pr-2">{line.content}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="flex divide-x" style={{ borderColor: 'var(--border)' }}>
      {renderHalf(leftLines, leftStyle, 'left')}
      {renderHalf(rightLines, rightStyle, 'right')}
    </div>
  );
}
