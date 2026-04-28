'use client';

import React from 'react';
import { SectionLabel, Card, Button, Badge } from '@/components/ui';
import { FileJson, FileText, Download, ShieldCheck } from 'lucide-react';

export default function OutputPanel({ results, reportUrl, downloadUrl }: { results: any, reportUrl?: string, downloadUrl?: string }) {
  return (
    <div className="space-y-6">
      <SectionLabel>Pipeline Artifacts</SectionLabel>
      
      {!results && (
        <div className="py-12 border border-dashed border-nexus-outline-variant flex flex-col items-center justify-center text-center gap-3">
          <ShieldCheck size={32} className="text-nexus-outline opacity-30" />
          <p className="text-[10px] font-bold uppercase tracking-widest text-nexus-outline">Results generation in progress...</p>
        </div>
      )}

      {results && (
        <div className="space-y-3">
          <Card variant="elevated" className="flex items-center justify-between p-4 group cursor-pointer hover:border-nexus-primary/40">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-nexus-surface border border-nexus-outline-variant flex items-center justify-center text-nexus-secondary">
                <FileText size={20} />
              </div>
              <div>
                <div className="text-xs font-bold uppercase tracking-wider">Accessibility Report</div>
                <div className="text-[10px] text-nexus-outline font-mono">PDF format • {results.pages_total} pages</div>
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
                <div className="text-xs font-bold uppercase tracking-wider">Source Patches</div>
                <div className="text-[10px] text-nexus-outline font-mono">ZIP archive • Clean HTML</div>
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
      )}

      <div className="pt-6 border-t border-nexus-outline-variant space-y-4">
        <SectionLabel>Summary Metrics</SectionLabel>
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 bg-nexus-surface-variant/30 border border-nexus-outline-variant">
            <div className="text-[9px] font-bold uppercase text-nexus-outline mb-1">Health Score</div>
            <div className="text-xl font-syne font-bold text-nexus-secondary">{results?.score_avg || '0'}%</div>
          </div>
          <div className="p-3 bg-nexus-surface-variant/30 border border-nexus-outline-variant">
            <div className="text-[9px] font-bold uppercase text-nexus-outline mb-1">Fix Rate</div>
            <div className="text-xl font-syne font-bold text-nexus-primary">{results?.fix_rate || '0'}%</div>
          </div>
        </div>
      </div>
    </div>
  );
}
