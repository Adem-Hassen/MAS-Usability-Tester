'use client';

import React, { useState } from 'react';
import { Card, SectionLabel, Badge, Button } from '@/components/ui';
import { Layout, AlertCircle, Zap, FileJson, Download, FileText } from 'lucide-react';
import clsx from 'clsx';
import IssuesPanel from '@/components/pipeline/IssuesPanel';
import PatchesPanel from '@/components/pipeline/PatchesPanel';
import DiffViewer from '@/components/diff/DiffViewer';
import { getFileContent, originalFileUrl, fixedFileUrl } from '@/lib/api';

interface OutputTabsProps {
  issues: any[];
  patches: any[];
  results: any;
  sessionId: string | null;
  status: string;
  reportUrl?: string;
  downloadUrl?: string;
  pageFilter: string | null;
  onFetchResults?: () => void;
}

function PreviewPanel({ results, sessionId, pageFilter }: { results: any, sessionId: string, pageFilter: string | null }) {
  const [originalHtml, setOriginalHtml] = useState<string | null>(null);
  const [fixedHtml, setFixedHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  // Use the first page if no filter is active
  const activePage = pageFilter || (results?.pages?.[0]?.page);

  React.useEffect(() => {
    if (!activePage || !sessionId || !results) {
      console.log('[PreviewPanel] Skipped load — missing:', { activePage, hasSessionId: !!sessionId, hasResults: !!results });
      return;
    }

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const pageData = results.pages?.find((p: any) => p.page === activePage) || results.pages?.[0];
        if (!pageData) {
          throw new Error(`No page data found. Results has ${results.pages?.length || 0} pages.`);
        }

        const originalFile = pageData.original_file || activePage;
        const fixedFile = pageData.fixed_file;

        if (!fixedFile) {
          throw new Error(`No fixed_file for page "${activePage}". Patch may not have been generated.`);
        }

        const originalUrl = originalFileUrl(sessionId, originalFile);
        const fixedUrl = fixedFileUrl(sessionId, fixedFile);

        console.log(`[PreviewPanel] Loading: original=${originalUrl}, fixed=${fixedUrl}`);

        const [orig, fixed] = await Promise.all([
          getFileContent(originalUrl).catch(e => {
            console.error('[PreviewPanel] Original fetch failed:', e);
            throw new Error(`Original file failed: ${e.message}`);
          }),
          getFileContent(fixedUrl).catch(e => {
            console.error('[PreviewPanel] Fixed fetch failed:', e);
            throw new Error(`Fixed file failed: ${e.message}`);
          })
        ]);

        console.log(`[PreviewPanel] Loaded: original=${orig.length} chars, fixed=${fixed.length} chars`);
        setOriginalHtml(orig);
        setFixedHtml(fixed);
      } catch (err: any) {
        console.error('[PreviewPanel] Load error:', err);
        setError(err.message || "Failed to load comparison data");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [activePage, sessionId, results, retryCount]);

  const handleRetry = () => {
    setRetryCount(c => c + 1);
  };

  if (!results) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center gap-4 text-nexus-outline">
        <Layout size={48} strokeWidth={1} />
        <div>
          <div className="text-sm font-bold uppercase tracking-widest text-white mb-2">Visual Regression</div>
          <p className="text-xs max-w-[240px]">Results not yet loaded. Wait for pipeline completion or click Refresh.</p>
          <button
            onClick={handleRetry}
            className="mt-3 text-[10px] font-bold uppercase tracking-widest px-3 py-1.5 bg-nexus-primary/20 border border-nexus-primary/30 text-nexus-primary hover:bg-nexus-primary/30 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>
    );
  }

  if (!results.pages || results.pages.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center gap-4 text-nexus-outline">
        <Layout size={48} strokeWidth={1} />
        <div>
          <div className="text-sm font-bold uppercase tracking-widest text-white mb-2">No Page Data</div>
          <p className="text-xs max-w-[240px]">Results loaded but contain no page entries.</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3">
        <div className="w-6 h-6 border-2 border-nexus-outline border-t-nexus-primary rounded-full animate-spin" />
        <div className="text-nexus-outline text-xs font-bold uppercase tracking-widest">Loading comparison...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-nexus-error text-center p-4 gap-3">
        <AlertCircle size={32} />
        <div className="text-sm font-bold uppercase">Error Loading Preview</div>
        <p className="text-xs opacity-70 max-w-[280px]">{error}</p>
        <button
          onClick={handleRetry}
          className="mt-2 text-[10px] font-bold uppercase tracking-widest px-3 py-1.5 bg-nexus-error/20 border border-nexus-error/30 text-nexus-error hover:bg-nexus-error/30 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!originalHtml || !fixedHtml) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center gap-4 text-nexus-outline">
        <Layout size={48} strokeWidth={1} />
        <div>
          <div className="text-sm font-bold uppercase tracking-widest text-white mb-2">Preview Unavailable</div>
          <p className="text-xs max-w-[240px]">HTML content could not be loaded.</p>
          <button
            onClick={handleRetry}
            className="mt-3 text-[10px] font-bold uppercase tracking-widest px-3 py-1.5 bg-nexus-primary/20 border border-nexus-primary/30 text-nexus-primary hover:bg-nexus-primary/30 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <SectionLabel>Live Comparison — {activePage}</SectionLabel>
        <button
          onClick={handleRetry}
          className="text-[9px] font-bold uppercase tracking-widest px-2 py-1 bg-white/5 border border-white/10 text-nexus-outline hover:text-white hover:border-white/20 transition-colors"
        >
          Refresh
        </button>
      </div>
      <div className="flex-1 min-h-0">
        <DiffViewer original={originalHtml} fixed={fixedHtml} filename={activePage} />
      </div>
    </div>
  );
}

export default function OutputTabs({
  issues,
  patches,
  results,
  sessionId,
  status,
  reportUrl,
  downloadUrl,
  pageFilter,
  onFetchResults,
}: OutputTabsProps) {
  const [activeTab, setActiveTab] = useState('issues');
  // Track selected page for the Verify tab (multi-page support)
  const [selectedVerifyPage, setSelectedVerifyPage] = useState<string | null>(null);

  const handleTabClick = (tabId: string) => {
    setActiveTab(tabId);
    if (tabId === 'preview' && onFetchResults) {
      console.log('[OutputTabs] Verify tab clicked — fetching results...');
      onFetchResults();
    }
  };

  // When results change with multiple pages, default to first page if none selected
  const availablePages = results?.pages?.map((p: any) => p.page as string) || [];
  const effectiveVerifyPage = selectedVerifyPage || pageFilter || availablePages[0] || null;

  const filteredIssues = pageFilter ? issues.filter(i => i.page === pageFilter) : issues;
  const filteredPatches = pageFilter ? patches.filter(p => p.page === pageFilter) : patches;

  const tabs = [
    { id: 'issues', label: 'Detection', icon: AlertCircle, count: filteredIssues.length, color: 'text-nexus-error' },
    { id: 'patches', label: 'Repairs', icon: Zap, count: filteredPatches.length, color: 'text-nexus-secondary' },
    { id: 'preview', label: 'Verify', icon: Layout, count: 0, color: 'text-nexus-primary' },
    { id: 'output', label: 'Export', icon: FileJson, count: 0, color: 'text-nexus-outline' },
  ];

  return (
    <div className="flex flex-col h-full bg-[#0E0F11] border-l border-nexus-outline-variant">
      {/* Refined Tab Headers */}
      <div className="flex bg-[#0A0B0D] border-b border-nexus-outline-variant/30">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
              <button
                key={tab.id}
                onClick={() => handleTabClick(tab.id)}
              className={clsx(
                "flex-1 flex flex-col items-center justify-center py-3 px-2 gap-1.5 transition-all relative group",
                isActive ? "text-white" : "text-nexus-outline hover:text-white/80"
              )}
            >
              <div className={clsx(
                "w-8 h-8 flex items-center justify-center transition-all duration-300",
                isActive ? "bg-white/5 scale-110" : "group-hover:bg-white/5"
              )}>
                <tab.icon size={14} className={clsx(isActive ? tab.color : "text-nexus-outline")} />
              </div>
              <span className="text-[9px] font-bold uppercase tracking-[0.15em]">{tab.label}</span>
              
              {/* Active Indicator */}
              {isActive && (
                <div className={clsx("absolute bottom-0 left-0 right-0 h-0.5", tab.color.replace('text-', 'bg-'))} />
              )}

              {tab.count > 0 && (
                <span className={clsx(
                  "absolute top-2 right-4 text-[8px] px-1 font-mono font-bold min-w-[14px] text-center",
                  isActive ? "bg-nexus-primary text-nexus-bg" : "bg-nexus-outline-variant text-nexus-outline"
                )}>
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-6">
        {activeTab === 'issues' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <SectionLabel className="mb-0">Detected Anomalies</SectionLabel>
              <Badge variant="neutral">{filteredIssues.length} Findings</Badge>
            </div>
            <IssuesPanel issues={filteredIssues} />
          </div>
        )}
        {activeTab === 'patches' && (
           <div className="space-y-6">
            <div className="flex items-center justify-between">
              <SectionLabel className="mb-0">Proposed Repairs</SectionLabel>
              <Badge variant="secondary">{filteredPatches.length} Patches</Badge>
            </div>
            <PatchesPanel patches={filteredPatches} />
          </div>
        )}
        {activeTab === 'preview' && (
          <div className="h-full flex flex-col space-y-4">
             <div className="flex items-center justify-between">
              <SectionLabel className="mb-0">Regression Analysis</SectionLabel>
              <div className="flex items-center gap-3">
                {/* Page selector — shown when multiple pages exist */}
                {availablePages.length > 1 && (
                  <div className="flex items-center gap-1">
                    <span className="text-[9px] font-mono text-nexus-outline uppercase">Page</span>
                    <div className="flex bg-black/60 border border-white/10 rounded-sm overflow-hidden">
                      {availablePages.map((pageName: string) => (
                        <button
                          key={pageName}
                          onClick={() => setSelectedVerifyPage(pageName)}
                          className={clsx(
                            'px-2 py-1 text-[9px] font-bold uppercase tracking-wider transition-all',
                            effectiveVerifyPage === pageName
                              ? 'bg-nexus-primary text-black'
                              : 'text-white/40 hover:text-white hover:bg-white/5'
                          )}
                        >
                          {pageName}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-mono text-nexus-outline uppercase">Confidence</span>
                  <div className="w-12 h-1 bg-nexus-surface-variant">
                    <div className="h-full bg-nexus-secondary w-[85%]" />
                  </div>
                </div>
              </div>
            </div>
            <div className="flex-1 min-h-0 bg-black/40 border border-white/5 p-1">
              <PreviewPanel results={results} sessionId={sessionId || ''} pageFilter={effectiveVerifyPage} />
            </div>
          </div>
        )}
        {activeTab === 'output' && (
          <div className="space-y-6">
            <SectionLabel>Export Results</SectionLabel>
            <div className="space-y-3">
              <Card variant="elevated" className="flex items-center justify-between p-4 group cursor-pointer hover:border-nexus-primary/40">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-nexus-surface border border-nexus-outline-variant flex items-center justify-center text-nexus-secondary">
                    <FileText size={20} />
                  </div>
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wider">Accessibility Report</div>
                    <div className="text-[10px] text-nexus-outline font-mono">PDF format • Comprehensive</div>
                  </div>
                </div>
                {reportUrl ? (
                  <Button variant="ghost" className="!p-2" href={reportUrl} download>
                    <Download size={16} />
                  </Button>
                ) : (
                  <Badge variant="neutral">Pending</Badge>
                )}
              </Card>

              <Card variant="elevated" className="flex items-center justify-between p-4 group cursor-pointer hover:border-nexus-primary/40">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-nexus-surface border border-nexus-outline-variant flex items-center justify-center text-nexus-primary">
                    <FileJson size={20} />
                  </div>
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wider">Patch Artifacts</div>
                    <div className="text-[10px] text-nexus-outline font-mono">ZIP archive • Source Code</div>
                  </div>
                </div>
                {downloadUrl ? (
                  <Button variant="ghost" className="!p-2" href={downloadUrl} download>
                    <Download size={16} />
                  </Button>
                ) : (
                  <Badge variant="neutral">Pending</Badge>
                )}
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
