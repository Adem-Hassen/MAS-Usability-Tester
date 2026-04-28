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
}

function PreviewPanel({ results, sessionId, pageFilter }: { results: any, sessionId: string, pageFilter: string | null }) {
  const [originalHtml, setOriginalHtml] = useState<string | null>(null);
  const [fixedHtml, setFixedHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Use the first page if no filter is active
  const activePage = pageFilter || (results?.pages?.[0]?.page);

  React.useEffect(() => {
    if (!activePage || !sessionId || !results) return;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const pageData = results.pages.find((p: any) => p.page === activePage) || results.pages[0];
        if (!pageData) throw new Error("Page results not found");

        const originalUrl = originalFileUrl(sessionId, pageData.original_file || activePage);
        const fixedUrl = fixedFileUrl(sessionId, pageData.fixed_file);

        console.log(`[PreviewPanel] Fetching: ${originalUrl} and ${fixedUrl}`);

        const [orig, fixed] = await Promise.all([
          getFileContent(originalUrl),
          getFileContent(fixedUrl)
        ]);

        setOriginalHtml(orig);
        setFixedHtml(fixed);
      } catch (err: any) {
        setError(err.message || "Failed to load comparison data");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [activePage, sessionId, results]);

  if (!results) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center gap-4 text-nexus-outline">
        <Layout size={48} strokeWidth={1} />
        <div>
          <div className="text-sm font-bold uppercase tracking-widest text-white mb-2">Visual Regression</div>
          <p className="text-xs max-w-[240px]">Live comparison preview will be available after the verification stage.</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-nexus-outline animate-pulse text-xs font-bold uppercase tracking-widest">Loading comparison...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-nexus-error text-center p-4">
        <AlertCircle size={32} className="mb-2" />
        <div className="text-sm font-bold uppercase mb-1">Error Loading Preview</div>
        <p className="text-xs opacity-70">{error}</p>
      </div>
    );
  }

  if (!originalHtml || !fixedHtml) return null;

  return (
    <div className="space-y-4 h-full flex flex-col">
      <SectionLabel>Live Comparison — {activePage}</SectionLabel>
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
}: OutputTabsProps) {
  const [activeTab, setActiveTab] = useState('issues');

  const filteredIssues = pageFilter ? issues.filter(i => i.page === pageFilter) : issues;
  const filteredPatches = pageFilter ? patches.filter(p => p.page === pageFilter) : patches;

  const tabs = [
    { id: 'issues', label: 'Issues', icon: AlertCircle, count: filteredIssues.length, color: 'text-nexus-error' },
    { id: 'patches', label: 'Patches', icon: Zap, count: filteredPatches.length, color: 'text-nexus-secondary' },
    { id: 'preview', label: 'Preview', icon: Layout, count: 0, color: 'text-nexus-primary' },
    { id: 'output', label: 'Export', icon: FileJson, count: 0, color: 'text-nexus-outline' },
  ];

  return (
    <div className="flex flex-col h-full bg-[#0E0F11] border-l border-nexus-outline-variant">
      {/* Tab Headers */}
      <div className="flex border-b border-nexus-outline-variant">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                "flex-1 flex flex-col items-center justify-center py-4 px-2 gap-1 border-b-2 transition-all relative",
                isActive ? "bg-nexus-primary/5 border-nexus-primary text-white" : "border-transparent text-nexus-outline hover:text-white hover:bg-white/5"
              )}
            >
              <tab.icon size={16} className={clsx(isActive ? tab.color : "text-nexus-outline")} />
              <span className="text-[10px] font-bold uppercase tracking-widest">{tab.label}</span>
              {tab.count > 0 && (
                <span className={clsx(
                  "absolute top-2 right-2 text-[8px] px-1 font-bold rounded-none",
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
        {activeTab === 'issues' && <IssuesPanel issues={filteredIssues} />}
        {activeTab === 'patches' && <PatchesPanel patches={filteredPatches} />}
        {activeTab === 'preview' && (
          <PreviewPanel results={results} sessionId={sessionId || ''} pageFilter={pageFilter} />
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
