'use client';

// src/app/page.tsx
// Main dashboard — three-panel layout during pipeline execution.
// Landing → Upload → [PipelineRail | AgentStream | OutputTabs]

import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import clsx from 'clsx';
import { usePipeline } from '@/hooks/usePipeline';
import { reportUrl, downloadUrl } from '@/lib/api';
import { Button, Spinner } from '@/components/ui';

import PipelineRail from '@/components/pipeline/PipelineRail';
import AgentStream  from '@/components/pipeline/AgentStream';
import OutputTabs   from '@/components/pipeline/OutputTabs';

// ─── Feature cards for landing page ───────────────────────────────────────────
const FEATURES = [
  {
    icon: '🔍',
    title: 'Detect',
    desc: 'WCAG 2.1 violations, contrast, labels, ARIA roles',
    gradient: 'from-red-500/10 to-transparent',
  },
  {
    icon: '🎭',
    title: 'Simulate',
    desc: 'Multi-persona browser simulation with Playwright',
    gradient: 'from-amber-500/10 to-transparent',
  },
  {
    icon: '🔧',
    title: 'Fix',
    desc: 'Auto-patch HTML attributes, CSS, and JavaScript',
    gradient: 'from-emerald-500/10 to-transparent',
  },
  {
    icon: '📊',
    title: 'Report',
    desc: 'Downloadable PDF with issues, patches, and scores',
    gradient: 'from-blue-500/10 to-transparent',
  },
];


// ─── Main Page ────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { state, upload, start, reset, fetchResults } = usePipeline();
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [pageFilter, setPageFilter] = useState<string | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<Map<string, string>>(new Map());

  const isIdle    = state.status === 'ready';
  const isRunning = state.status === 'running' || state.status === 'queued';
  const isDone    = state.status === 'done';
  const isFailed  = state.status === 'failed';
  const isActive  = !isIdle;

  // Collect pages from all event sources
  const allPages = Array.from(new Set([
    ...state.issues.map(i => i.page),
    ...state.patches.map(p => p.page),
    ...(state.results?.pages.map(p => p.page) ?? []),
  ])).filter(Boolean);

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
      await upload(accepted);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Upload failed';
      setUploadErr(msg);
    } finally {
      setUploading(false);
    }
  }, [upload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'text/html': ['.html'] },
    maxFiles: 5,
    disabled: isRunning || uploading,
  });

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

        {state.jobId && (
          <span className="text-xs font-mono hidden md:block" style={{ color: 'var(--text3)' }}>
            job / {state.jobId}
          </span>
        )}

        <div className="ml-auto flex items-center gap-3">
          {isRunning && (
            <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--amber)' }}>
              <Spinner size={14} />
              <span className="hidden sm:inline">Processing</span>
              <span className="font-mono">{state.progress}%</span>
            </div>
          )}
          {isDone && (
            <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--ok)' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              Complete — {state.results?.pages_total ?? state.fileCount} pages
            </div>
          )}
          {isFailed && (
            <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--danger)' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              Failed{state.errorStage ? ` at ${state.errorStage}` : ''}
            </div>
          )}
          {(isDone || isFailed) && (
            <Button variant="ghost" onClick={reset}>New Session</Button>
          )}
          {isDone && state.reportUrl && (
            <Button variant="primary" href={state.reportUrl} download>
              ↓ PDF Report
            </Button>
          )}
          {isDone && state.downloadUrl && (
            <Button variant="ghost" href={state.downloadUrl} download>
              ↓ ZIP
            </Button>
          )}
        </div>
      </header>

      {/* ── Main Content ── */}
      <div className="flex-1 flex flex-col">

        {/* ── Landing / Idle state ── */}
        {isIdle && (
          <div className="flex-1 flex flex-col items-center justify-center px-6 py-16 animate-fade-in">
            <h1 className="font-display font-bold text-4xl md:text-5xl mb-4 tracking-tight text-center"
                style={{ color: 'var(--text)' }}>
              Accessibility Evaluator
            </h1>
            <p className="text-base md:text-lg max-w-xl leading-relaxed mb-12 text-center"
               style={{ color: 'var(--text2)' }}>
              Drop up to 5 HTML files to automatically detect WCAG violations,
              simulate real user interactions, apply targeted fixes, and receive
              a comprehensive accessibility report.
            </p>

            {/* Upload zone */}
            <div
              {...getRootProps()}
              className={clsx(
                'w-full max-w-xl rounded-2xl border-2 border-dashed p-8 text-center cursor-pointer',
                'transition-all duration-300 select-none',
                isDragActive
                  ? 'border-amber-400/70 bg-amber-400/5 scale-[1.02] shadow-lg shadow-amber-400/10'
                  : uploading
                  ? 'border-zinc-800 opacity-50 cursor-not-allowed'
                  : 'border-zinc-700 hover:border-amber-400/40 hover:bg-zinc-900/40 hover:shadow-lg hover:shadow-amber-400/5'
              )}
            >
              <input {...getInputProps()} />
              <div className="text-4xl mb-3 opacity-60">
                {uploading ? '⏳' : isDragActive ? '📥' : '📄'}
              </div>
              <p className="text-base font-display font-semibold mb-1" style={{ color: 'var(--text)' }}>
                {uploading ? 'Uploading…' : isDragActive ? 'Release to upload' : 'Drop HTML files here'}
              </p>
              <p className="text-sm" style={{ color: 'var(--text3)' }}>
                Up to 5 files · .html only · Max 5 MB each
              </p>
            </div>

            {uploadErr && (
              <div className="mt-4 text-xs px-4 py-2.5 rounded-lg border animate-slide-up max-w-xl w-full"
                   style={{ background: 'rgba(224,90,74,0.08)',
                            borderColor: 'rgba(224,90,74,0.25)', color: 'var(--danger)' }}>
                ⚠ {uploadErr}
              </div>
            )}

            {/* Feature cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-3xl w-full mt-12">
              {FEATURES.map(({ icon, title, desc, gradient }) => (
                <div key={title}
                     className={clsx(
                       'rounded-xl p-4 text-center border transition-all',
                       'hover:border-amber-400/20 hover:scale-[1.02]',
                       `bg-gradient-to-b ${gradient}`
                     )}
                     style={{ borderColor: 'var(--border)' }}>
                  <div className="text-2xl mb-2">{icon}</div>
                  <div className="text-sm font-display font-semibold mb-1.5"
                       style={{ color: 'var(--text)' }}>{title}</div>
                  <div className="text-xs leading-relaxed" style={{ color: 'var(--text3)' }}>{desc}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Active session — Three-panel layout ── */}
        {isActive && (
          <div className="max-w-screen-2xl mx-auto w-full px-4 md:px-6 py-6 flex gap-5 flex-1 min-h-0">

            {/* Left: Pipeline Rail */}
            <aside className="w-60 flex-shrink-0 hidden lg:block">
              <PipelineRail
                steps={state.steps}
                progress={state.progress}
                progressLabel={state.progressLabel}
                isRunning={isRunning}
                connection={state.connection}
                model={state.model}
                totalIssues={state.totalIssues}
                totalPatches={state.totalPatches}
              />

              {/* Page filter */}
              {allPages.length > 0 && (
                <div className="rounded-xl border p-4 mt-4"
                     style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>
                  <div className="text-[10px] font-mono font-semibold uppercase tracking-widest mb-3"
                       style={{ color: 'var(--text3)' }}>
                    Filter by page
                  </div>
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

              {/* Re-upload zone (minimal) */}
              <div className="mt-4">
                <div
                  {...getRootProps()}
                  className={clsx(
                    'rounded-xl border-2 border-dashed p-3 text-center cursor-pointer transition-all select-none',
                    isDragActive ? 'border-amber-400/70 bg-amber-400/5' :
                    isRunning || uploading ? 'border-zinc-800 opacity-40 cursor-not-allowed' :
                    'border-zinc-700/50 hover:border-amber-400/30 hover:bg-zinc-900/30'
                  )}
                >
                  <input {...getInputProps()} />
                  <p className="text-xs" style={{ color: 'var(--text3)' }}>
                    {isRunning ? 'Running…' : 'Drop new files'}
                  </p>
                </div>
              </div>
            </aside>

            {/* Center: Agent Stream */}
            <div className="flex-1 min-w-0 flex flex-col gap-4">
              {/* Mobile progress bar */}
              {isRunning && (
                <div className="lg:hidden space-y-1.5">
                  <div className="flex justify-between text-xs font-mono" style={{ color: 'var(--text3)' }}>
                    <span className="truncate mr-2 flex-1">{state.progressLabel}</span>
                    <span style={{ color: 'var(--amber)' }}>{state.progress}%</span>
                  </div>
                  <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--surface)' }}>
                    <div className="h-full rounded-full transition-all duration-700"
                         style={{ width: `${state.progress}%`, background: 'var(--amber)' }} />
                  </div>
                </div>
              )}

              <AgentStream logs={state.logs} isRunning={isRunning} />

              {/* Output tabs below the stream on smaller screens */}
              <div className="xl:hidden">
                <OutputTabs
                  issues={state.issues}
                  patches={state.patches}
                  results={state.results}
                  sessionId={state.jobId}
                  uploadedFiles={uploadedFiles}
                  status={state.status}
                  error={state.error}
                  errorStage={state.errorStage}
                  reportUrl={state.reportUrl}
                  downloadUrl={state.downloadUrl}
                  onFetchResults={fetchResults}
                  pageFilter={pageFilter}
                />
              </div>
            </div>

            {/* Right: Output Tabs (visible on xl screens) */}
            <aside className="w-[420px] flex-shrink-0 hidden xl:block overflow-y-auto">
              <OutputTabs
                issues={state.issues}
                patches={state.patches}
                results={state.results}
                sessionId={state.jobId}
                uploadedFiles={uploadedFiles}
                status={state.status}
                error={state.error}
                errorStage={state.errorStage}
                reportUrl={state.reportUrl}
                downloadUrl={state.downloadUrl}
                onFetchResults={fetchResults}
                pageFilter={pageFilter}
              />
            </aside>

          </div>
        )}
      </div>
    </div>
  );
}
