'use client';

import React from 'react';
import { Card, Badge, SectionLabel } from '@/components/ui';
import { Zap, Code, FileCode, CheckCircle2, ChevronRight } from 'lucide-react';

interface Patch {
  patch_id: string;
  target: string;
  description: string;
  patch_type: string;
  page: string;
}

export default function PatchesPanel({ patches }: { patches: Patch[] }) {
  if (patches.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center text-nexus-outline gap-4 py-20">
        <div className="w-16 h-16 bg-nexus-surface border border-nexus-outline-variant flex items-center justify-center rounded-none opacity-50">
          <Zap size={32} />
        </div>
        <div className="space-y-1">
          <div className="text-xs font-bold uppercase tracking-widest text-white">No Patches Generated</div>
          <p className="text-[10px] max-w-[200px]">Waiting for the recommender agent to propose fixes.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionLabel>Proposed Repairs</SectionLabel>
      <div className="space-y-3">
        {patches.map((patch) => (
          <Card key={patch.patch_id} variant="elevated" className="!p-0 overflow-hidden group cursor-pointer border-l-2 border-l-transparent hover:border-l-nexus-secondary">
            <div className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <Zap size={14} className="text-nexus-secondary" />
                    <span className="text-xs font-bold uppercase tracking-tight truncate">{patch.patch_type || 'Patch'}</span>
                  </div>
                  <div className="text-[10px] text-nexus-outline font-mono truncate">{patch.target}</div>
                </div>
                <div className="w-6 h-6 bg-nexus-secondary/10 border border-nexus-secondary/20 flex items-center justify-center text-nexus-secondary">
                  <CheckCircle2 size={12} />
                </div>
              </div>
              <p className="text-[11px] text-white/60 leading-relaxed line-clamp-3 font-mono bg-black/20 p-2 border border-white/5">
                {patch.description}
              </p>
            </div>
            <div className="px-4 py-2 bg-white/5 border-t border-nexus-outline-variant flex items-center justify-between group-hover:bg-nexus-secondary/10 transition-colors">
              <div className="flex items-center gap-2">
                <FileCode size={12} className="text-nexus-outline" />
                <span className="text-[9px] font-bold uppercase tracking-widest text-nexus-outline">{patch.page || 'Global'}</span>
              </div>
              <ChevronRight size={14} className="text-nexus-outline group-hover:text-nexus-secondary" />
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
