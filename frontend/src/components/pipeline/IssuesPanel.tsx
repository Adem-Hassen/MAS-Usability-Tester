'use client';

import React from 'react';
import { Card, Badge, SectionLabel } from '@/components/ui';
import { AlertCircle, AlertTriangle, Info, ChevronRight } from 'lucide-react';
import clsx from 'clsx';

interface Issue {
  issue_id: string;
  title: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  category: string;
  description: string;
  page: string;
}

export default function IssuesPanel({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center text-nexus-outline gap-4 py-20">
        <div className="w-16 h-16 bg-nexus-surface border border-nexus-outline-variant flex items-center justify-center rounded-none opacity-50">
          <AlertCircle size={32} />
        </div>
        <div className="space-y-1">
          <div className="text-xs font-bold uppercase tracking-widest text-white">No Issues Detected</div>
          <p className="text-[10px] max-w-[200px]">Waiting for agents to finish their persona simulations.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionLabel>Detected Violations</SectionLabel>
      <div className="space-y-3">
        {issues.map((issue) => (
          <Card key={issue.issue_id} variant="elevated" className="!p-0 overflow-hidden group cursor-pointer border-l-2 border-l-transparent hover:border-l-nexus-error">
            <div className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <SeverityIcon severity={issue.severity} />
                    <span className="text-xs font-bold uppercase tracking-tight truncate">{issue.title}</span>
                  </div>
                  <div className="text-[10px] text-nexus-outline font-mono truncate">{issue.page}</div>
                </div>
                <Badge variant={issue.severity === 'critical' ? 'error' : issue.severity === 'high' ? 'tertiary' : 'primary'}>
                  {issue.severity}
                </Badge>
              </div>
              <p className="text-[11px] text-white/60 leading-relaxed line-clamp-2">
                {issue.description}
              </p>
            </div>
            <div className="px-4 py-2 bg-white/5 border-t border-nexus-outline-variant flex items-center justify-between group-hover:bg-nexus-primary/10 transition-colors">
              <span className="text-[9px] font-bold uppercase tracking-widest text-nexus-outline">{issue.category}</span>
              <ChevronRight size={14} className="text-nexus-outline group-hover:text-nexus-primary" />
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

function SeverityIcon({ severity }: { severity: string }) {
  switch (severity) {
    case 'critical': return <AlertCircle size={14} className="text-nexus-error" />;
    case 'high': return <AlertTriangle size={14} className="text-nexus-tertiary" />;
    case 'medium': return <Info size={14} className="text-nexus-primary" />;
    default: return <Info size={14} className="text-nexus-outline" />;
  }
}
