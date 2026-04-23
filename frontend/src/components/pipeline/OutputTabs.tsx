'use client';

// src/components/pipeline/OutputTabs.tsx
// Right panel — tabbed output with Issues, Patches, Results, and Metrics sub-tabs.

import { useState, useEffect, useRef } from 'react';
import clsx from 'clsx';
import dynamic from 'next/dynamic';
import { Tabs, Badge, SectionLabel, SeverityBadge, Button, Spinner, EmptyState } from '@/components/ui';
import { fixedFileUrl, reportPdfUrl, reportUrl, downloadUrl } from '@/lib/api';
import type { Issue, Patch, PageResult, SessionResults, Severity } from '@/types';

const DiffViewer  = dynamic(() => import('@/components/diff/DiffViewer'),  { ssr: false });
const HtmlPreview = dynamic(() => import('@/components/preview/HtmlPreview'), { ssr: false });

// ── Score Ring ────────────────────────────────────────────────────────────────
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

// ── Issues Panel ──────────────────────────────────────────────────────────────
function IssuesPanel({ issues }: { issues: Issue[] }) {
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

// ── Patches Panel ─────────────────────────────────────────────────────────────
function PatchesPanel({ patches }: { patches: Patch[] }) {
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

// ── Page Result Card ──────────────────────────────────────────────────────────
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
          <Tabs tabs={tabs} active={tab} onChange={t => setTab(t as 'summary' | 'diff' | 'preview')} />
        </div>
      )}

      {/* Tab content */}
      <div className="p-5">
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

        {tab === 'diff' && (
          loadingFixed ? (
            <div className="flex items-center justify-center py-16 gap-3"
                 style={{ color: 'var(--text3)' }}>
              <Spinner /> Loading diff…
            </div>
          ) : fixedHtml && originalHtml ? (
            <DiffViewer original={originalHtml} fixed={fixedHtml} filename={result.fixed_file} />
          ) : (
            <EmptyState icon="📄" title="Original file not available for diff"
              description="Diff requires the original HTML to be loaded client-side." />
          )
        )}

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

// ── Main OutputTabs Component ─────────────────────────────────────────────────
export interface OutputTabsProps {
  issues:         Issue[];
  patches:        Patch[];
  results:        SessionResults | null;
  sessionId:      string | null;
  uploadedFiles:  Map<string, string>;
  status:         string;
  error:          string | null;
  errorStage:     string | null;
  reportUrl?:     string;
  downloadUrl?:   string;
  onFetchResults: () => void;
  pageFilter:     string | null;
}

export default function OutputTabs({
  issues, patches, results, sessionId, uploadedFiles,
  status, error, errorStage, reportUrl: rUrl, downloadUrl: dUrl,
  onFetchResults, pageFilter,
}: OutputTabsProps) {
  const [activeTab, setActiveTab] = useState('progress');

  const isDone   = status === 'done';
  const isFailed = status === 'failed';

  // Auto-switch to results when done
  useEffect(() => {
    if (isDone) {
      setActiveTab('results');
      if (!results) onFetchResults();
    }
  }, [isDone]);

  const filterData = <T extends { page: string }>(arr: T[]) =>
    pageFilter ? arr.filter(x => x.page === pageFilter) : arr;

  const tabs = [
    { id: 'progress', label: 'Progress',  count: 0 },
    { id: 'issues',   label: 'Issues',    count: issues.length },
    { id: 'patches',  label: 'Patches',   count: patches.length },
    { id: 'results',  label: 'Results',   count: results?.pages.length ?? 0 },
  ];

  return (
    <div className="space-y-4">
      <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

      {/* Progress tab — show AgentStream */}
      {activeTab === 'progress' && (
        <div className="text-sm text-center py-8" style={{ color: 'var(--text3)' }}>
          {/* AgentStream is rendered separately in the main layout */}
          <p>Logs are displayed in the Agent Stream panel →</p>
        </div>
      )}

      {/* Issues tab */}
      {activeTab === 'issues' && (
        <IssuesPanel issues={filterData(issues)} />
      )}

      {/* Patches tab */}
      {activeTab === 'patches' && (
        <PatchesPanel patches={filterData(patches)} />
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
                 style={{ color: 'var(--danger)' }}>
                Pipeline failed{errorStage ? ` at ${errorStage}` : ''}
              </p>
              <p className="text-xs" style={{ color: 'var(--text2)' }}>{error}</p>
            </div>
          )}

          {/* Download buttons */}
          {isDone && sessionId && (
            <div className="flex items-center gap-3">
              {rUrl && <Button variant="primary" href={rUrl} download>↓ PDF Report</Button>}
              {dUrl && <Button variant="ghost" href={dUrl} download>↓ Download ZIP</Button>}
            </div>
          )}

          {!results && isDone && (
            <div className="flex items-center justify-center py-16 gap-3"
                 style={{ color: 'var(--text3)' }}>
              <Spinner /> Loading results…
            </div>
          )}
          {results?.pages
            .filter(p => !pageFilter || p.page === pageFilter)
            .map(page => (
              <PageResultCard
                key={page.page}
                result={page}
                sessionId={sessionId!}
                originalHtml={uploadedFiles.get(page.page)}
              />
            ))
          }
        </div>
      )}
    </div>
  );
}
