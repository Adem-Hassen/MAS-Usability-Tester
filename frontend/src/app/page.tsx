'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { useDropzone } from 'react-dropzone';
import clsx from 'clsx';
import dynamic from 'next/dynamic';
import { usePipeline } from '@/hooks/usePipeline';
import { fixedFileUrl, reportPdfUrl } from '@/lib/api';
import {
  Card, Badge, Button, Spinner, EmptyState, Tabs, SectionLabel, SeverityBadge
} from '@/components/ui';
import type { Severity, PageResult } from '@/types';

// Dynamic imports — avoid SSR issues with browser-only APIs
const DiffViewer  = dynamic(() => import('@/components/diff/DiffViewer'),  { ssr: false });
const HtmlPreview = dynamic(() => import('@/components/preview/HtmlPreview'), { ssr: false });

// ─── Pipeline step row ────────────────────────────────────────────────────────


function StepRow({ step }: {
  step: { id: string; label: string; status: string; page?: string }
}) {
  const dotCls: Record<string, string> = {
    idle:    'w-2 h-2 rounded-full bg-zinc-700',
    running: 'w-2 h-2 rounded-full bg-amber-400 animate-pulse shadow-[0_0_8px_rgba(200,169,110,0.7)]',
    done:    'w-2 h-2 rounded-full bg-emerald-500',
    error:   'w-2 h-2 rounded-full bg-red-500',
  };
  const textCls: Record<string, string> = {
    idle:    'text-zinc-600',
    running: 'text-amber-300 font-medium',
    done:    'text-zinc-400',
    error:   'text-red-400',
  };
  return (
    <div className="flex items-center gap-2.5 py-1.5 group">
      <span className={dotCls[step.status] ?? dotCls.idle} />
      <span className={clsx('text-sm transition-colors flex-1', textCls[step.status] ?? textCls.idle)}>
        {step.label}
      </span>
      {step.status === 'running' && step.page && (
        <span className="text-[10px] font-mono text-amber-500/70 truncate max-w-[100px]">
          {step.page}
        </span>
      )}
      {step.status === 'done' && (
        <span className="text-[10px] text-emerald-600">✓</span>
      )}
    </div>
  );
}

// ─── Score ring ───────────────────────────────────────────────────────────────
function ScoreRing({ score }: { score: number }) {
  const r    = 34;
  const circ = 2 * Math.PI * r;
  const dash = Math.max(0, Math.min(1, score / 10)) * circ;
  const col  = score >= 7 ? '#4a9a6a' : score >= 4 ? '#d4844a' : '#e05a4a';
  return (
    <div className="relative inline-flex items-center justify-center flex-shrink-0">
      <svg width="80" height="80" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r={r} fill="none" stroke="#2d2d29" strokeWidth="5.5" />
        <circle cx="40" cy="40" r={r} fill="none" stroke={col} strokeWidth="5.5"
          strokeDasharray={`${dash} ${circ - dash}`} strokeLinecap="round"
          transform="rotate(-90 40 40)"
          style={{ transition: 'stroke-dasharray 1s cubic-bezier(.4,0,.2,1)' }} />
      </svg>
      <div className="absolute text-center leading-tight">
        <div className="font-display font-bold text-lg leading-none" style={{ color: col }}>
          {score.toFixed(1)}
        </div>
        <div className="text-[9px] font-mono" style={{ color: 'var(--text3)' }}>/10</div>
      </div>
    </div>
  );
}

// ─── Page result card ─────────────────────────────────────────────────────────
function PageResultCard({
  result, sessionId, originalHtml
}: {
  result: PageResult;
  sessionId: string;
  originalHtml?: string;
}) {
  const [tab, setTab]           = useState<'summary' | 'diff' | 'preview'>('summary');
  const [fixedHtml, setFixedHtml] = useState<string | null>(null);
  const [loadingFixed, setLoadingFixed] = useState(false);

  const hasFix = !!result.fixed_file;

  // Lazy-load fixed HTML when diff/preview tab is selected
  useEffect(() => {
    if ((tab === 'diff' || tab === 'preview') && hasFix && !fixedHtml) {
      setLoadingFixed(true);
      fetch(fixedFileUrl(sessionId, result.fixed_file!))
        .then(r => r.text())
        .then(setFixedHtml)
        .catch(() => setFixedHtml('<!-- Could not load fixed HTML -->'))
        .finally(() => setLoadingFixed(false));
    }
  }, [tab, hasFix, fixedHtml, sessionId, result.fixed_file]);

  const tabs = [
    { id: 'summary', label: 'Summary' },
    ...(hasFix ? [
      { id: 'diff',    label: 'Diff' },
      { id: 'preview', label: 'Preview' },
    ] : []),
  ];

  return (
    <div className="rounded-xl border overflow-hidden animate-slide-up"
         style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>

      {/* Header */}
      <div className="flex items-center gap-4 px-5 py-4 border-b"
           style={{ background: 'var(--bg3)', borderColor: 'var(--border)' }}>
        {result.overall_score != null && !result.error && (
          <ScoreRing score={result.overall_score} />
        )}
        <div className="flex-1 min-w-0">
          <div className="font-display font-bold text-xl tracking-tight mb-1"
               style={{ color: 'var(--text)' }}>
            {result.page}
          </div>
          {result.error ? (
            <span className="text-sm" style={{ color: 'var(--danger)' }}>
              ⚠ {result.error}
            </span>
          ) : (
            <div className="flex items-center gap-4 text-sm" style={{ color: 'var(--text2)' }}>
              <span>{result.total_issues ?? 0} issues detected</span>
              <span style={{ color: 'var(--text3)' }}>·</span>
              <span>{result.patches_applied ?? 0} patches applied</span>
            </div>
          )}
        </div>
        <div className="flex gap-2 flex-shrink-0">
          {result.fixed_file && (
            <Button variant="ghost" href={fixedFileUrl(sessionId, result.fixed_file)} download>
              ↓ Fixed HTML
            </Button>
          )}
        </div>
      </div>

      {/* Tab bar */}
      {tabs.length > 1 && (
        <div className="px-5 pt-4">
          <Tabs tabs={tabs} active={tab} onChange={t => setTab(t as any)} />
        </div>
      )}

      {/* Tab content */}
      <div className="p-5">
        {/* Summary */}
        {tab === 'summary' && (
          <div className="space-y-4">
            {result.summary && (
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text2)' }}>
                {result.summary}
              </p>
            )}
            {result.recommendations && result.recommendations.length > 0 && (
              <div>
                <SectionLabel>Top Recommendations</SectionLabel>
                <ol className="space-y-2">
                  {result.recommendations.map((rec, i) => (
                    <li key={i} className="flex gap-3 text-sm">
                      <span className="font-mono text-amber-500 flex-shrink-0 w-5 text-right">
                        {i + 1}.
                      </span>
                      <span style={{ color: 'var(--text2)' }}>{rec}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {!result.summary && !result.recommendations?.length && !result.error && (
              <EmptyState icon="📋" title="No summary available" />
            )}
          </div>
        )}

        {/* Diff */}
        {tab === 'diff' && (
          loadingFixed ? (
            <div className="flex items-center justify-center py-16 gap-3"
                 style={{ color: 'var(--text3)' }}>
              <Spinner /> Loading diff…
            </div>
          ) : fixedHtml && originalHtml ? (
            <DiffViewer
              original={originalHtml}
              fixed={fixedHtml}
              filename={result.fixed_file}
            />
          ) : (
            <EmptyState icon="📄" title="Original file not available for diff"
              description="Diff requires the original HTML to be loaded client-side." />
          )
        )}

        {/* Preview */}
        {tab === 'preview' && (
          loadingFixed ? (
            <div className="flex items-center justify-center py-16 gap-3"
                 style={{ color: 'var(--text3)' }}>
              <Spinner /> Loading preview…
            </div>
          ) : fixedHtml ? (
            <HtmlPreview
              original={originalHtml ?? fixedHtml}
              fixed={fixedHtml}
              filename={result.fixed_file}
              fixedFileUrl={fixedFileUrl(sessionId, result.fixed_file!)}
            />
          ) : (
            <EmptyState icon="🖼" title="Could not load preview" />
          )
        )}
      </div>
    </div>
  );
}

// ─── Live log ─────────────────────────────────────────────────────────────────
function LiveLog({ logs }: { logs: Array<{ level: string; message: string; ts: string }> }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs.length]);

  return (
    <div className="rounded-xl border flex flex-col overflow-hidden"
         style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>
      <div className="px-4 py-2.5 border-b flex items-center justify-between"
           style={{ background: 'var(--bg3)', borderColor: 'var(--border)' }}>
        <SectionLabel>Live Log</SectionLabel>
        <span className="text-[10px] font-mono" style={{ color: 'var(--text3)' }}>
          {logs.length} entries
        </span>
      </div>
      <div className="overflow-y-auto flex-1 p-4 space-y-0.5 font-mono text-xs"
           style={{ maxHeight: '420px' }}>
        {logs.length === 0 && (
          <div className="py-8 text-center" style={{ color: 'var(--text3)' }}>
            Waiting for pipeline events…
          </div>
        )}
        {logs.map((log, i) => (
          <div key={i} className="flex gap-3 items-start py-0.5 animate-fade-in">
            <span style={{ color: 'var(--text3)' }}>
              {new Date(log.ts).toLocaleTimeString([], { hour12: false })}
            </span>
            <span className={clsx(
              'uppercase text-[9px] font-bold w-10 pt-px flex-shrink-0',
              log.level === 'error'   ? 'text-red-500' :
              log.level === 'warning' ? 'text-amber-500' : 'text-emerald-600'
            )}>
              {log.level.slice(0, 4)}
            </span>
            <span style={{ color: 'var(--text2)' }}>{log.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

// ─── Issues panel ─────────────────────────────────────────────────────────────
function IssuesPanel({ issues }: { issues: ReturnType<typeof usePipeline>['state']['issues'] }) {
  const bySeverity = ['critical', 'high', 'medium', 'low'] as Severity[];
  return (
    <div className="space-y-2">
      {issues.length === 0 && (
        <EmptyState icon="🔍" title="No issues detected yet"
          description="Issues will appear here as personas simulate interactions." />
      )}
      {bySeverity.flatMap(sev =>
        issues
          .filter(i => i.severity === sev)
          .map((issue, i) => (
            <div key={issue.issue_id || i}
                 className="rounded-xl border p-4 animate-slide-up hover:border-amber-400/15 transition-colors"
                 style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>
              <div className="flex items-start gap-3">
                <SeverityBadge severity={issue.severity} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium mb-0.5" style={{ color: 'var(--text)' }}>
                    {issue.title}
                  </div>
                  <div className="text-xs leading-relaxed mb-2" style={{ color: 'var(--text2)' }}>
                    {issue.description}
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="neutral">{issue.category}</Badge>
                    {issue.page && (
                      <span className="text-[10px] font-mono" style={{ color: 'var(--text3)' }}>
                        {issue.page}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))
      )}
    </div>
  );
}

// ─── Patches panel ────────────────────────────────────────────────────────────
function PatchesPanel({ patches }: { patches: ReturnType<typeof usePipeline>['state']['patches'] }) {
  const typeMap: Record<string, 'teal' | 'info' | 'amber'> = {
    html_attribute: 'teal',
    css_snippet:    'info',
    js_snippet:     'amber',
  };
  return (
    <div className="space-y-2">
      {patches.length === 0 && (
        <EmptyState icon="🔧" title="No patches yet"
          description="Patches will appear here as fixes are applied." />
      )}
      {patches.map((patch, i) => (
        <div key={patch.patch_id || i}
             className="rounded-xl border p-4 animate-slide-up"
             style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>
          <div className="flex items-start gap-3">
            <Badge variant={typeMap[patch.patch_type] ?? 'neutral'}>
              {patch.patch_type?.replace(/_/g, ' ')}
            </Badge>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-mono mb-1" style={{ color: 'var(--amber)' }}>
                {patch.target}
              </div>
              <div className="text-sm" style={{ color: 'var(--text2)' }}>
                {patch.description}
              </div>
              {patch.page && (
                <div className="mt-1 text-[10px] font-mono" style={{ color: 'var(--text3)' }}>
                  {patch.page}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { state, upload, start, reset, fetchResults } = usePipeline();
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('progress');
  const [pageFilter, setPageFilter] = useState<string | null>(null);

  // Uploaded files for diff (original content)
  const [uploadedFiles, setUploadedFiles] = useState<Map<string, string>>(new Map());

  const isIdle    = state.status === 'ready';
  const isRunning = state.status === 'running';
  const isDone    = state.status === 'done';
  const isFailed  = state.status === 'failed';

  // Switch to results when done
  useEffect(() => {
    if (isDone) {
      setActiveTab('results');
      if (!state.results) fetchResults();
    }
  }, [isDone]);

  // Collect pages from all event sources
  const allPages = Array.from(new Set([
    ...state.issues.map(i => i.page),
    ...state.patches.map(p => p.page),
    ...(state.results?.pages.map(p => p.page) ?? []),
  ])).filter(Boolean);

  const filterData = <T extends { page: string }>(arr: T[]) =>
    pageFilter ? arr.filter(x => x.page === pageFilter) : arr;

  // ── Dropzone ────────────────────────────────────────────────────────────
  const onDrop = useCallback(async (accepted: File[]) => {
    setUploadErr(null);
    if (!accepted.length) return;
    if (accepted.length > 5) { setUploadErr('Maximum 5 HTML files.'); return; }
    for (const f of accepted) {
      if (!f.name.toLowerCase().endsWith('.html')) {
        setUploadErr(`"${f.name}" is not an HTML file.`); return;
      }
    }

    // Read originals for diff viewer
    const map = new Map<string, string>();
    await Promise.all(accepted.map(f =>
      f.text().then(txt => map.set(f.name.replace(/\.html$/i, ''), txt))
    ));
    setUploadedFiles(map);

    setUploading(true);
    try {
      const sid = await upload(accepted);
      await start(sid);
      setActiveTab('progress');
    } catch (e: any) {
      setUploadErr(e.message);
    } finally {
      setUploading(false);
    }
  }, [upload, start]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'text/html': ['.html'] },
    maxFiles: 5,
    disabled: isRunning || uploading,
  });

  const tabs = [
    { id: 'progress', label: 'Progress',  count: 0 },
    { id: 'issues',   label: 'Issues',    count: state.issues.length },
    { id: 'patches',  label: 'Patches',   count: state.patches.length },
    { id: 'results',  label: 'Results',   count: state.results?.pages.length ?? 0 },
  ];

  return (
    <div className="relative min-h-screen flex flex-col" style={{ zIndex: 1 }}>

      {/* ── Topbar ── */}
      <header
        className="h-14 border-b sticky top-0 z-20 flex items-center px-6 gap-6"
        style={{ background: 'rgba(15,15,13,0.92)', backdropFilter: 'blur(12px)',
                 borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2.5 flex-shrink-0">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center font-display font-black text-sm"
               style={{ background: 'var(--amber)', color: '#0f0f0d' }}>
            N
          </div>
          <span className="font-display font-bold text-base tracking-tight">VerSimUX</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded font-mono hidden sm:inline"
                style={{ background: 'var(--surface)', color: 'var(--text3)' }}>
            Accessibility Evaluator
          </span>
        </div>

        {state.sessionId && (
          <span className="text-xs font-mono hidden md:block" style={{ color: 'var(--text3)' }}>
            session / {state.sessionId}
          </span>
        )}

        <div className="ml-auto flex items-center gap-3">
          {isRunning && (
            <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--amber)' }}>
              <Spinner size={14} />
              Processing {state.pages_done}/{state.input_paths_count ?? '?'}
            </div>
          )}
          {isDone && (
            <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--ok)' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              Complete — {state.results?.pages_total ?? 0} pages evaluated
            </div>
          )}
          {isFailed && (
            <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--danger)' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              Failed
            </div>
          )}
          {(isDone || isFailed) && (
            <Button variant="ghost" onClick={reset}>New Session</Button>
          )}
          {isDone && state.sessionId && (
            <Button variant="primary"
                    href={reportPdfUrl(state.sessionId)} download>
              ↓ PDF Report
            </Button>
          )}
        </div>
      </header>

      <div className="max-w-screen-xl mx-auto w-full px-6 py-8 flex gap-6 flex-1">

        {/* ── Left sidebar ── */}
        <aside className="w-68 flex-shrink-0 space-y-4" style={{ width: '268px' }}>

          {/* Upload dropzone */}
          

          {uploadErr && (
            <div className="text-xs px-3 py-2 rounded-lg border animate-slide-up"
                 style={{ background: 'rgba(224,90,74,0.08)',
                          borderColor: 'rgba(224,90,74,0.25)', color: 'var(--danger)' }}>
              ⚠ {uploadErr}
            </div>
          )}

          {/* Pipeline steps */}
          {!isIdle && (
            <div className="rounded-xl border p-4 animate-fade-in"
                 style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>
              <SectionLabel>Pipeline</SectionLabel>
              {state.steps.map(s => <StepRow key={s.id} step={s} />)}
            </div>
          )}

          {/* Progress bar */}
          {isRunning && (
            <div className="space-y-1.5 animate-fade-in">
              <div className="flex justify-between text-xs font-mono"
                   style={{ color: 'var(--text3)' }}>
                <span className="truncate mr-2 flex-1">{state.progressLabel}</span>
                <span>{state.progress}%</span>
              </div>
              <div className="h-1 rounded-full overflow-hidden" style={{ background: 'var(--surface)' }}>
                <div className="h-full rounded-full transition-all duration-700"
                     style={{ width: `${state.progress}%`, background: 'var(--amber)' }} />
              </div>
            </div>
          )}

          {/* Page filter */}
          {allPages.length > 0 && (
            <div className="rounded-xl border p-4"
                 style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>
              <SectionLabel>Filter by page</SectionLabel>
              <div className="space-y-0.5">
                <button
                  onClick={() => setPageFilter(null)}
                  className={clsx(
                    'w-full text-left text-xs px-2.5 py-1.5 rounded-md transition-colors',
                    !pageFilter ? 'bg-amber-400/10 text-amber-300' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
                  )}
                >
                  All pages ({allPages.length})
                </button>
                {allPages.map(p => (
                  <button
                    key={p}
                    onClick={() => setPageFilter(p === pageFilter ? null : p)}
                    className={clsx(
                      'w-full text-left text-xs px-2.5 py-1.5 rounded-md font-mono truncate transition-colors',
                      pageFilter === p ? 'bg-amber-400/10 text-amber-300' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Stats summary */}
          {(state.issues.length > 0 || state.patches.length > 0) && (
            <div className="rounded-xl border p-4 grid grid-cols-2 gap-3"
                 style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>
              {[
                { label: 'Issues',  value: state.issues.length,  color: 'var(--danger)' },
                { label: 'Patches', value: state.patches.length, color: 'var(--ok)' },
                { label: 'Critical', value: state.issues.filter(i => i.severity === 'critical').length, color: '#e05a4a' },
                { label: 'High',     value: state.issues.filter(i => i.severity === 'high').length,     color: 'var(--warning)' },
              ].map(({ label, value, color }) => (
                <div key={label} className="text-center">
                  <div className="font-display font-bold text-xl" style={{ color }}>{value}</div>
                  <div className="text-[10px] font-mono" style={{ color: 'var(--text3)' }}>{label}</div>
                </div>
              ))}
            </div>
          )}
        </aside>

        {/* ── Main area ── */}
        <main className="flex-1 min-w-0 space-y-4">

          {/* Idle landing */}
          {isIdle && (
            <div className="flex flex-col items-center justify-center py-20 text-center animate-fade-in">
              
              <h1 className="font-display font-bold text-4xl mb-3 tracking-tight"
                  style={{ color: 'var(--text)' }}>
                Accessibility Evaluator
              </h1>
              <p className="text-base max-w-lg leading-relaxed mb-10"
                 style={{ color: 'var(--text2)' }}>
                Drop up to 5 HTML files to automatically detect WCAG violations,
                simulate real user interactions, apply targeted fixes, and receive
                a comprehensive accessibility report.
              </p>
              <div className="grid grid-cols-4 gap-4 max-w-2xl w-full">
                {[
                  ['', 'Detect', 'WCAG 2.1 violations, contrast, labels, ARIA'],
                  ['', 'Simulate', 'Multi-persona browser simulation with Playwright'],
                  ['', 'Fix',     'Auto-patch HTML attributes, CSS, and JavaScript'],
                  ['', 'Report',  'Downloadable PDF with issues, patches, scores'],
                ].map(([icon, title, desc]) => (
                  <div key={title} className="rounded-xl p-4 text-center border transition-all hover:border-amber-400/20"
                       style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>
                    <div className="text-2xl mb-2">{icon}</div>
                    <div className="text-sm font-display font-semibold mb-1.5"
                         style={{ color: 'var(--text)' }}>{title}</div>
                    <div className="text-xs leading-relaxed" style={{ color: 'var(--text3)' }}>{desc}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Active session */}
          {!isIdle && (
            <>
              <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

              {/* Progress tab */}
              {activeTab === 'progress' && <LiveLog logs={state.logs} />}

              {/* Issues tab */}
              {activeTab === 'issues' && (
                <IssuesPanel issues={filterData(state.issues)} />
              )}

              {/* Patches tab */}
              {activeTab === 'patches' && (
                <PatchesPanel patches={filterData(state.patches)} />
              )}

              {/* Results tab */}
              {activeTab === 'results' && (
                <div className="space-y-6">
                  {isFailed && (
                    <div className="rounded-xl border p-6 text-center"
                         style={{ background: 'rgba(224,90,74,0.06)',
                                  borderColor: 'rgba(224,90,74,0.2)' }}>
                      <div className="text-3xl mb-3">⚠</div>
                      <p className="text-sm font-medium mb-1"
                         style={{ color: 'var(--danger)' }}>Pipeline failed</p>
                      <p className="text-xs" style={{ color: 'var(--text2)' }}>{state.error}</p>
                    </div>
                  )}
                  {!state.results && isDone && (
                    <div className="flex items-center justify-center py-16 gap-3"
                         style={{ color: 'var(--text3)' }}>
                      <Spinner /> Loading results…
                    </div>
                  )}
                  {state.results?.pages
                    .filter(p => !pageFilter || p.page === pageFilter)
                    .map((page, i) => (
                      <PageResultCard
                        key={page.page}
                        result={page}
                        sessionId={state.sessionId!}
                        originalHtml={uploadedFiles.get(page.page)}
                      />
                    ))
                  }
                </div>
              )}
              
            </>
          )}
          <div
            {...getRootProps()}
            className={clsx(
              'rounded-xl border-2 border-dashed p-5 text-center cursor-pointer transition-all select-none',
              isDragActive ? 'border-amber-400/70 bg-amber-400/5 scale-[1.01]' :
              isRunning || uploading ? 'border-zinc-800 opacity-50 cursor-not-allowed' :
              'border-zinc-700 hover:border-amber-400/40 hover:bg-zinc-900/40'
            )}
          >
            <input {...getInputProps()} />
            <div className="text-2xl mb-2">
              {uploading ? '' : isDragActive ? '' : isRunning ? '' : ''}
            </div>
            <p className="text-sm font-medium mb-0.5" style={{ color: 'var(--text)' }}>
              {uploading ? 'Uploading…' :
               isRunning  ? 'Pipeline running' :
               isDragActive ? 'Release to upload' : 'Drop HTML files here'}
            </p>
            <p className="text-xs" style={{ color: 'var(--text3)' }}>
              {isRunning ? 'Processing in progress' : 'Up to 5 files · .html only'}
            </p>
          </div>
        </main>
        
      </div>
    </div>
  );
}
