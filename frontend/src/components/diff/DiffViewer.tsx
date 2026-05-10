'use client';

// src/components/diff/DiffViewer.tsx
// Professional GitHub-style diff viewer with side-by-side / unified modes,
// synchronized scrolling, HTML syntax highlighting, word-level diffs,
// sticky headers, and fullscreen support.

import { useMemo, useState, useRef, useEffect, useCallback } from 'react';
import clsx from 'clsx';
import { Maximize2, Minimize2, Columns, FileText, ChevronDown, ChevronRight, X } from 'lucide-react';
import { useFullscreen } from '@/hooks/useFullscreen';

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

/* ── Simple Myers diff (LCS) ─────────────────────────────────────────── */

function computeDiff(a: string, b: string): DiffLine[] {
  const aLines = a.split('\n');
  const bLines = b.split('\n');

  const m = aLines.length;
  const n = bLines.length;
  const capM = Math.min(m, 800);
  const capN = Math.min(n, 800);

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

  const seq: Array<['eq' | 'del' | 'ins', string]> = [];
  let i = capM, j = capN;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && aLines[i - 1] === bLines[j - 1]) {
      seq.push(['eq', aLines[i - 1]]); i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      seq.push(['ins', bLines[j - 1]]); j--;
    } else {
      seq.push(['del', aLines[i - 1]]); i--;
    }
  }
  seq.reverse();

  const lines: DiffLine[] = [];
  let leftNo = 1, rightNo = 1;
  for (const [kind, content] of seq) {
    if (kind === 'eq') {
      lines.push({ kind: 'equal', content, lineNo: { left: leftNo++, right: rightNo++ } });
    } else if (kind === 'del') {
      lines.push({ kind: 'removed', content, lineNo: { left: leftNo++ } });
    } else {
      lines.push({ kind: 'added', content, lineNo: { right: rightNo++ } });
    }
  }

  // Append overflow
  if (m > capM) {
    for (let k = capM; k < m; k++) {
      lines.push({ kind: 'equal', content: aLines[k], lineNo: { left: leftNo++, right: rightNo++ } });
    }
  }
  if (n > capN) {
    for (let k = capN; k < n; k++) {
      lines.push({ kind: 'equal', content: bLines[k], lineNo: { left: leftNo++, right: rightNo++ } });
    }
  }

  return lines;
}

/* ── Word-level diff for inline highlights ───────────────────────────── */

function wordDiff(oldText: string, newText: string): Array<{ type: 'eq' | 'del' | 'ins'; text: string }> {
  // Simple word-level diff using space/token split
  const oldWords = oldText.split(/(\s+)/);
  const newWords = newText.split(/(\s+)/);
  const m = oldWords.length;
  const n = newWords.length;
  const capM = Math.min(m, 200);
  const capN = Math.min(n, 200);

  const dp: number[][] = Array.from({ length: capM + 1 }, () => new Array(capN + 1).fill(0));
  for (let i = 1; i <= capM; i++) {
    for (let j = 1; j <= capN; j++) {
      dp[i][j] = oldWords[i - 1] === newWords[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  const seq: Array<['eq' | 'del' | 'ins', string]> = [];
  let i = capM, j = capN;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldWords[i - 1] === newWords[j - 1]) {
      seq.push(['eq', oldWords[i - 1]]); i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      seq.push(['ins', newWords[j - 1]]); j--;
    } else {
      seq.push(['del', oldWords[i - 1]]); i--;
    }
  }
  seq.reverse();
  return seq.map(([type, text]) => ({ type, text }));
}

/* ── HTML syntax highlighter ─────────────────────────────────────────── */

function highlightHtml(line: string): React.ReactNode[] {
  const tokens: React.ReactNode[] = [];
  const tagRegex = /(<\/?)([\w-]+)([^>]*)>/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tagRegex.exec(line)) !== null) {
    const [full, slash, tagName, attrs] = match;
    const start = match.index;

    if (start > lastIndex) {
      tokens.push(<span key={`t${lastIndex}`} className="text-zinc-300">{line.slice(lastIndex, start)}</span>);
    }

    tokens.push(
      <span key={`tag${start}`}>
        <span className="text-zinc-500">{slash}</span>
        <span className="text-rose-400 font-medium">{tagName}</span>
        {highlightAttrs(attrs)}
        <span className="text-zinc-500">{'>'}</span>
      </span>
    );

    lastIndex = start + full.length;
  }

  if (lastIndex < line.length) {
    tokens.push(<span key={`t${lastIndex}`} className="text-zinc-300">{line.slice(lastIndex)}</span>);
  }

  return tokens.length ? tokens : [<span key="empty" className="text-zinc-300">{line}</span>];
}

function highlightAttrs(attrString: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const regex = /(\s+)([\w-]+)(=)("[^"]*"|'[^']*')/g;
  let m: RegExpExecArray | null;
  let last = 0;

  while ((m = regex.exec(attrString)) !== null) {
    const [full, space, name, eq, value] = m;
    const idx = m.index;
    if (idx > last) {
      out.push(<span key={`as${last}`} className="text-zinc-400">{attrString.slice(last, idx)}</span>);
    }
    out.push(
      <span key={`a${idx}`}>
        <span className="text-zinc-500">{space}</span>
        <span className="text-amber-400">{name}</span>
        <span className="text-zinc-500">{eq}</span>
        <span className="text-emerald-400">{value}</span>
      </span>
    );
    last = idx + full.length;
  }

  if (last < attrString.length) {
    out.push(<span key={`as${last}`} className="text-zinc-400">{attrString.slice(last)}</span>);
  }
  return out;
}

/* ── Main component ──────────────────────────────────────────────────── */

export default function DiffViewer({ original, fixed, filename }: DiffViewerProps) {
  const [mode, setMode] = useState<'split' | 'unified'>('split');
  const [showContext, setShowContext] = useState(true);
  const [wrapLines, setWrapLines] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { isFullscreen, toggle: toggleFullscreen, exit: exitFullscreen } = useFullscreen(containerRef);

  const diff = useMemo(() => computeDiff(original, fixed), [original, fixed]);

  const stats = useMemo(() => ({
    changed: diff.filter(l => l.kind !== 'equal').length,
    added: diff.filter(l => l.kind === 'added').length,
    removed: diff.filter(l => l.kind === 'removed').length,
  }), [diff]);

  if (original === fixed) {
    return (
      <div className="rounded-none border border-nexus-outline-variant p-8 text-center bg-nexus-surface space-y-3">
        <div className="text-2xl text-nexus-secondary">✓</div>
        <p className="text-sm text-nexus-outline">No changes — file is identical to original.</p>
        <p className="text-[10px] text-nexus-outline/60 font-mono">Both files are {original.length.toLocaleString()} characters.</p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={clsx(
        'flex flex-col overflow-hidden bg-[#0d1117]',
        isFullscreen ? 'fixed inset-0 z-[9999]' : 'rounded-none border border-nexus-outline-variant'
      )}
    >
      {/* Sticky Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-white/10 bg-[#161b22] shrink-0">
        {filename && (
          <div className="flex items-center gap-2">
            <FileText size={12} className="text-nexus-primary" />
            <span className="text-[11px] font-bold text-white">{filename}</span>
          </div>
        )}

        <div className="flex items-center gap-2 text-[11px] font-mono">
          <span className="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-800/40">+{stats.added}</span>
          <span className="px-1.5 py-0.5 rounded bg-red-950/60 text-red-400 border border-red-800/40">−{stats.removed}</span>
          <span className="text-zinc-500">{stats.changed} changes</span>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setWrapLines(v => !v)}
            className={clsx(
              'text-[10px] font-bold uppercase tracking-wider px-2 py-1 transition-colors border',
              wrapLines ? 'text-nexus-primary bg-nexus-primary/10 border-nexus-primary/30' : 'text-zinc-500 border-white/10 hover:text-white'
            )}
          >
            Wrap
          </button>
          <button
            onClick={() => setShowContext(v => !v)}
            className={clsx(
              'text-[10px] font-bold uppercase tracking-wider px-2 py-1 transition-colors border',
              showContext ? 'text-nexus-primary bg-nexus-primary/10 border-nexus-primary/30' : 'text-zinc-500 border-white/10 hover:text-white'
            )}
          >
            Context
          </button>
          <div className="flex border border-white/10">
            {(['split', 'unified'] as const).map(m => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={clsx(
                  'text-[10px] font-bold tracking-wider px-2.5 py-1 capitalize transition-colors flex items-center gap-1',
                  mode === m ? 'bg-nexus-primary/20 text-nexus-primary' : 'text-zinc-500 hover:text-white'
                )}
              >
                {m === 'split' && <Columns size={10} />}
                {m}
              </button>
            ))}
          </div>
          <button
            onClick={toggleFullscreen}
            className={`text-[12px] font-bold ${isFullscreen ? 'hover:text-red-400 hover:border-red-400/30' : 'hover:text-white hover:border-white/20'} uppercase tracking-wider px-2 py-1 border border-white/10  transition-colors flex items-center gap-1`}
            title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          >
            {isFullscreen ? <Minimize2  size={14} /> : <Maximize2 size={16} />}
            {isFullscreen ? 'Exit' : ''}
          </button>
          
        </div>
      </div>

      {/* Diff content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {mode === 'unified' ? (
          <UnifiedView diff={diff} showContext={showContext} wrapLines={wrapLines} />
        ) : (
          <SplitView diff={diff} showContext={showContext} wrapLines={wrapLines} />
        )}
      </div>
    </div>
  );
}

/* ── Unified view ────────────────────────────────────────────────────── */

function UnifiedView({ diff, showContext, wrapLines }: {
  diff: DiffLine[];
  showContext: boolean;
  wrapLines: boolean;
}) {
  const visible = useMemo(() => {
    if (!showContext) return diff.map((l, i) => ({ ...l, idx: i }));
    const changed = new Set(diff.map((l, i) => l.kind !== 'equal' ? i : -1).filter(i => i >= 0));
    const vis = new Set<number>();
    for (const idx of changed) {
      for (let k = Math.max(0, idx - 3); k <= Math.min(diff.length - 1, idx + 3); k++) vis.add(k);
    }
    return diff.map((l, i) => ({ ...l, idx: i, hidden: !vis.has(i) }));
  }, [diff, showContext]);

  const gutterW = 'w-14';

  return (
    <div className="h-full overflow-auto">
      <table className="w-full border-collapse font-mono text-[13px] leading-6" style={{ tableLayout: 'fixed' }}>
        <tbody>
          {visible.map((line, i) => {
            if ('hidden' in line && line.hidden) {
              const prev = visible[i - 1];
              const isFirstHidden = !prev || !('hidden' in prev && prev.hidden);
              if (!isFirstHidden) return null;
              return (
                <tr key={`fold-${i}`}>
                  <td colSpan={4} className="py-2 text-center">
                    <span className="inline-flex items-center gap-1 px-3 py-1 text-[11px] text-zinc-600 bg-[#161b22] border border-white/5 rounded">
                      <ChevronDown size={10} />
                      Context hidden
                    </span>
                  </td>
                </tr>
              );
            }

            const isAdd = line.kind === 'added';
            const isDel = line.kind === 'removed';
            const bg = isAdd ? 'bg-emerald-950/30' : isDel ? 'bg-red-950/30' : 'bg-transparent';
            const sign = isAdd ? '+' : isDel ? '−' : ' ';
            const signColor = isAdd ? 'text-emerald-500' : isDel ? 'text-red-500' : 'text-zinc-700';
            const contentColor = isAdd ? 'text-emerald-200' : isDel ? 'text-red-200' : 'text-zinc-400';

            return (
              <tr key={line.idx ?? i} className={clsx('hover:bg-white/[0.02] transition-colors', bg)}>
                {/* Left line no */}
                <td className={clsx(gutterW, 'text-right pr-3 select-none py-0 text-zinc-600 bg-[#0d1117] border-r border-white/5 sticky left-0')}> 
                  {line.lineNo.left ?? ''}
                </td>
                {/* Right line no */}
                <td className={clsx(gutterW, 'text-right pr-3 select-none py-0 text-zinc-600 bg-[#0d1117] border-r border-white/5 sticky left-14')}>
                  {line.lineNo.right ?? ''}
                </td>
                {/* Sign */}
                <td className={clsx('w-8 text-center select-none py-0 font-bold', signColor)}>
                  {sign}
                </td>
                {/* Content */}
                <td className={clsx('py-0 pr-4', contentColor, wrapLines ? 'whitespace-pre-wrap break-all' : 'whitespace-pre overflow-hidden')}> 
                  {line.kind === 'equal'
                    ? highlightHtml(line.content)
                    : <InlineDiff oldText={isDel ? line.content : ''} newText={isAdd ? line.content : ''} kind={line.kind} />}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ── Split view with synchronized scrolling ──────────────────────────── */

function SplitView({ diff, showContext, wrapLines }: {
  diff: DiffLine[];
  showContext: boolean;
  wrapLines: boolean;
}) {
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const isSyncing = useRef(false);

  const syncScroll = useCallback((source: HTMLDivElement, target: HTMLDivElement) => {
    if (isSyncing.current) return;
    isSyncing.current = true;
    target.scrollTop = source.scrollTop;
    requestAnimationFrame(() => { isSyncing.current = false; });
  }, []);

  useEffect(() => {
    const l = leftRef.current;
    const r = rightRef.current;
    if (!l || !r) return;

    const onLeft = () => syncScroll(l, r);
    const onRight = () => syncScroll(r, l);

    l.addEventListener('scroll', onLeft, { passive: true });
    r.addEventListener('scroll', onRight, { passive: true });
    return () => {
      l.removeEventListener('scroll', onLeft);
      r.removeEventListener('scroll', onRight);
    };
  }, [syncScroll]);

  // Build aligned rows
  const rows = useMemo(() => {
    const result: Array<{
      left?: DiffLine;
      right?: DiffLine;
      kind: 'eq' | 'pair' | 'gap';
    }> = [];

    let i = 0, j = 0;
    while (i < diff.length || j < diff.length) {
      const li = diff[i];
      const ri = diff[j];

      if (li && li.kind === 'equal' && ri && ri.kind === 'equal') {
        result.push({ left: li, right: ri, kind: 'eq' });
        i++; j++;
      } else if (li && li.kind === 'removed') {
        // Look ahead for matching added
        let k = j;
        while (k < diff.length && diff[k].kind === 'added') k++;
        if (k > j) {
          // Pair removed with added
          for (let a = 0; a < Math.max(k - j, 1); a++) {
            result.push({
              left: li,
              right: diff[j + a],
              kind: 'pair',
            });
          }
          if (k - j > 1) i++; // consumed one removed per row
          else { i++; j++; }
        } else {
          result.push({ left: li, kind: 'gap' });
          i++;
        }
      } else if (ri && ri.kind === 'added') {
        result.push({ right: ri, kind: 'gap' });
        j++;
      } else {
        i++; j++;
      }
    }
    return result;
  }, [diff]);

  // Filter context
  const visibleRows = useMemo(() => {
    if (!showContext) return rows.map((r, i) => ({ ...r, idx: i }));
    const changed = new Set(rows.map((r, i) =>
      (r.left && r.left.kind !== 'equal') || (r.right && r.right.kind !== 'equal') ? i : -1
    ).filter(i => i >= 0));
    const vis = new Set<number>();
    for (const idx of changed) {
      for (let k = Math.max(0, idx - 3); k <= Math.min(rows.length - 1, idx + 3); k++) vis.add(k);
    }
    return rows.map((r, i) => ({ ...r, idx: i, hidden: !vis.has(i) }));
  }, [rows, showContext]);

  const renderHalf = (
    lines: Array<{ line?: DiffLine; isLeft: boolean }>,
    ref: React.Ref<HTMLDivElement>,
    side: 'left' | 'right'
  ) => (
    <div ref={ref} className="flex-1 overflow-auto min-w-0">
      {/* Sticky header */}
      <div className="sticky top-0 z-10 px-3 py-2 text-[10px] uppercase tracking-widest font-bold border-b border-white/10 text-zinc-400 bg-[#161b22] flex items-center gap-2">
        <FileText size={10} />
        {side === 'left' ? 'Original' : 'Patched'}
      </div>
      <div className="font-mono text-[13px] leading-6">
        {lines.map((item, i) => {
          const line = item.line;
          if (!line) {
            // Empty placeholder for alignment
            return (
              <div key={`empty-${i}`} className="flex min-h-[24px]">
                <span className="w-14 text-right pr-3 select-none flex-shrink-0 text-zinc-700 bg-[#0d1117] border-r border-white/5">…</span>
                <span className="flex-1 px-2 text-zinc-800"> </span>
              </div>
            );
          }
          const isAdd = line.kind === 'added';
          const isDel = line.kind === 'removed';
          const bg = isAdd ? 'bg-emerald-950/30' : isDel ? 'bg-red-950/30' : 'bg-transparent';
          const textColor = isAdd ? 'text-emerald-200' : isDel ? 'text-red-200' : 'text-zinc-400';
          const lineNo = side === 'left' ? line.lineNo.left : line.lineNo.right;

          return (
            <div key={`${line.kind}-${i}`} className={clsx('flex min-h-[24px] hover:bg-white/[0.02]', bg)}>
              <span className="w-14 text-right pr-3 select-none flex-shrink-0 text-zinc-600 bg-[#0d1117] border-r border-white/5">
                {lineNo ?? ''}
              </span>
              <span className={clsx('flex-1 px-2', textColor, wrapLines ? 'whitespace-pre-wrap break-all' : 'whitespace-pre overflow-hidden')}>
                {line.kind === 'equal'
                  ? highlightHtml(line.content)
                  : <InlineDiff oldText={isDel ? line.content : ''} newText={isAdd ? line.content : ''} kind={line.kind} />}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );

  // Build left/right line arrays from visible rows
  const leftLines = visibleRows.map((r, i) => ({
    line: r.left,
    isLeft: true,
    hidden: 'hidden' in r ? r.hidden : false,
  })).filter(item => !item.hidden);

  const rightLines = visibleRows.map((r, i) => ({
    line: r.right,
    isLeft: false,
    hidden: 'hidden' in r ? r.hidden : false,
  })).filter(item => !item.hidden);

  return (
    <div className="flex h-full divide-x divide-white/10">
      {renderHalf(leftLines, leftRef, 'left')}
      {renderHalf(rightLines, rightRef, 'right')}
    </div>
  );
}

/* ── Inline word diff renderer ───────────────────────────────────────── */

function InlineDiff({ oldText, newText, kind }: { oldText: string; newText: string; kind: LineKind }) {
  if (kind === 'equal') return <>{highlightHtml(oldText)}</>;

  const parts = wordDiff(oldText || '', newText || '');
  return (
    <>
      {parts.map((part, i) => {
        if (part.type === 'eq') {
          return <span key={i} className="text-zinc-400">{part.text}</span>;
        }
        if (part.type === 'del') {
          return (
            <span key={i} className="bg-red-500/20 text-red-300 px-0.5 rounded">
              {part.text}
            </span>
          );
        }
        return (
          <span key={i} className="bg-emerald-500/20 text-emerald-300 px-0.5 rounded">
            {part.text}
          </span>
        );
      })}
    </>
  );
}
