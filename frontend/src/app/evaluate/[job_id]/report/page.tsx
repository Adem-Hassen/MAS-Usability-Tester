'use client';

import React, { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { usePipeline } from '@/hooks/usePipeline';
import { Sidebar, Header } from '@/components/layout';
import { Card, SectionLabel, Badge, MetricCard, Button } from '@/components/ui';
import { FileText, Download, Share2, AlertCircle, Zap, ShieldCheck, ArrowLeft, ChevronRight } from 'lucide-react';
import clsx from 'clsx';

export default function ReportPage() {
  const { job_id } = useParams();
  const router = useRouter();
  const { state, fetchResults, connect, reset } = usePipeline();

  useEffect(() => {
    if (job_id && typeof job_id === 'string') {
      if (!state.jobId) {
        connect(job_id);
      }
      fetchResults();
    }
  }, [job_id, connect, fetchResults, state.jobId]);

  const handleNext = () => {
    reset();
    router.push('/');
  };

  const results = state.results;

  return (
    <div className="flex min-h-screen bg-nexus-bg font-sans text-white">
      <Sidebar />
      
      <main className="flex-1 ml-sidebar flex flex-col">
        <Header />

        <div className="p-10 max-w-6xl w-full mx-auto space-y-12 pb-24">
          
          {/* Back Button & Title */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <button 
                onClick={() => router.push(`/evaluate/${job_id}`)}
                className="flex items-center gap-2 text-nexus-outline hover:text-white transition-colors text-xs font-bold uppercase tracking-widest mb-4"
              >
                <ArrowLeft size={14} />
                Back to Session
              </button>
              <h1 className="text-4xl font-syne font-bold tracking-tight">Accessibility Audit Report</h1>
              <div className="flex items-center gap-2 text-nexus-outline font-mono text-sm">
                <span>Job ID:</span>
                <span className="text-nexus-primary">{job_id}</span>
                <span className="mx-2">/</span>
                <span>Date: {new Date().toLocaleDateString()}</span>
              </div>
            </div>
            <div className="flex gap-3">
              <Button variant="secondary" className="gap-2" onClick={handleNext}>
                <Zap size={16} />
                NEXT EVALUATION
              </Button>
              <Button variant="primary" className="gap-2" href={state.reportUrl || `/api/v1/evaluate/${job_id}/report`} download>
                <Download size={16} />
                DOWNLOAD PDF
              </Button>
            </div>
          </div>

          {/* Executive Summary */}
          <div className="grid grid-cols-4 gap-6">
            <MetricCard 
              label="Overall Health" 
              value={`${results?.score_avg || '0'}%`} 
              variant="secondary"
              subtext="System compliance score"
            />
            <MetricCard 
              label="Violations" 
              value={results?.issues_total || state.totalIssues || '0'} 
              variant="error"
              subtext="Across all personas"
            />
            <MetricCard 
              label="Repairs Applied" 
              value={results?.patches_total || state.totalPatches || '0'} 
              variant="primary"
              subtext="Auto-generated patches"
            />
            <MetricCard 
              label="Pages Audited" 
              value={results?.pages_total || '0'} 
              variant="base"
              subtext="Total unique routes"
            />
          </div>

          {/* Detailed Breakdown */}
          <div className="grid grid-cols-12 gap-10">
            
            {/* Left Column: Issues Categorization */}
            <div className="col-span-7 space-y-8">
              <SectionLabel>Detected Violations by Category</SectionLabel>
              <div className="space-y-4">
                {results?.pages?.map((page: any, i: number) => (
                  <Card key={i} variant="elevated" className="group cursor-pointer hover:border-nexus-primary/40">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 flex items-center justify-center border bg-nexus-primary/10 border-nexus-primary/20 text-nexus-primary">
                          <FileText size={20} />
                        </div>
                        <div>
                          <div className="text-sm font-bold uppercase tracking-wide">{page.page}</div>
                          <div className="text-[10px] text-nexus-outline font-mono">Score: {page.overall_score}%</div>
                        </div>
                      </div>
                      <Badge variant={page.overall_score < 70 ? 'error' : 'success'}>
                        {page.total_issues} Issues
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between pt-4 border-t border-nexus-outline-variant/30">
                      <div className="text-xs text-nexus-outline line-clamp-1 flex-1 mr-4 italic">
                        {page.summary || "No summary available"}
                      </div>
                      <div 
                        onClick={() => router.push(`/evaluate/${job_id}`)}
                        className="flex items-center gap-2 text-nexus-outline text-[10px] font-bold uppercase tracking-widest group-hover:text-white transition-colors"
                      >
                        View Details
                        <ChevronRight size={14} />
                      </div>
                    </div>
                  </Card>
                )) || (
                  <div className="text-center py-12 border border-dashed border-nexus-outline-variant text-nexus-outline uppercase text-[10px] font-bold tracking-widest">
                    No page data available
                  </div>
                )}
              </div>
            </div>

            {/* Right Column: Health Trend & Stats */}
            <div className="col-span-5 space-y-8">
              <SectionLabel>Validation Integrity</SectionLabel>
              <Card className="p-8 flex flex-col items-center justify-center text-center space-y-6">
                <div className="relative w-32 h-32">
                  <svg className="w-full h-full" viewBox="0 0 100 100">
                    <circle 
                      cx="50" cy="50" r="45" 
                      fill="none" 
                      stroke="currentColor" 
                      strokeWidth="8" 
                      className="text-nexus-surface-variant" 
                    />
                    <circle 
                      cx="50" cy="50" r="45" 
                      fill="none" 
                      stroke="currentColor" 
                      strokeWidth="8" 
                      strokeDasharray="283" 
                      strokeDashoffset={283 - (283 * (results?.score_avg || 0) / 100)}
                      strokeLinecap="square"
                      className="text-nexus-secondary" 
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-2xl font-syne font-bold">{results?.score_avg || 0}%</span>
                    <span className="text-[8px] font-bold uppercase tracking-widest text-nexus-outline">Pass Rate</span>
                  </div>
                </div>
                <div className="space-y-2">
                  <h3 className="text-lg font-syne font-bold">Audit Verified</h3>
                  <p className="text-xs text-nexus-outline max-w-xs">
                    {results?.summary || "All persona simulations completed. The system has analyzed accessibility violations and generated optimized patches."}
                  </p>
                </div>
                <div className="w-full pt-6 border-t border-nexus-outline-variant/30 flex justify-between">
                  <div className="text-left">
                    <div className="text-[9px] font-bold uppercase text-nexus-outline mb-1">Fix Rate</div>
                    <div className="text-lg font-syne font-bold text-nexus-primary">{results?.fix_rate || 0}%</div>
                  </div>
                  <div className="text-right">
                    <div className="text-[9px] font-bold uppercase text-nexus-outline mb-1">Patches</div>
                    <div className="text-lg font-syne font-bold text-nexus-secondary">{results?.patches_total || 0}</div>
                  </div>
                </div>
              </Card>

              <Card variant="elevated" className="p-6 bg-nexus-primary/5 border-nexus-primary/20">
                <div className="flex items-center gap-3 mb-4 text-nexus-primary">
                  <ShieldCheck size={20} />
                  <span className="text-xs font-bold uppercase tracking-widest">System Integrity</span>
                </div>
                <div className="font-mono text-[9px] text-nexus-outline break-all bg-black/20 p-3 uppercase">
                  Session: {job_id}
                </div>
              </Card>
            </div>

          </div>

        </div>
      </main>
    </div>
  );
}
