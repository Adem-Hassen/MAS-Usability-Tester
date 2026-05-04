'use client';

import React, { useEffect } from 'react';
import { useParams } from 'next/navigation';
import { usePipeline } from '@/hooks/usePipeline';
import { Sidebar, Header } from '@/components/layout';
import { Button } from '@/components/ui';
import { FileText, Zap } from 'lucide-react';
import clsx from 'clsx';
import PipelineRail from '@/components/pipeline/PipelineRail';
import AgentStream from '@/components/pipeline/AgentStream';
import OutputTabs from '@/components/pipeline/OutputTabs';
import { LivePreviewPanel } from '@/components/pipeline/LivePreviewPanel';

export default function EvaluatePage() {
  const { job_id } = useParams();
  const { state, fetchResults, connect, reset } = usePipeline();
  const [isSidebarCollapsed, setIsSidebarCollapsed] = React.useState(false);
  const isRunning = state.status === 'running' || state.status === 'queued';

  useEffect(() => {
    if (job_id && typeof job_id === 'string') {
      connect(job_id);
    }
  }, [job_id, connect]);

  useEffect(() => {
    if (state.status === 'done') {
      fetchResults();
    }
  }, [state.status, fetchResults]);

  return (
    <div className="flex h-screen bg-nexus-bg font-sans text-white overflow-hidden">
      <Sidebar 
        isCollapsed={isSidebarCollapsed} 
        onToggle={() => setIsSidebarCollapsed(!isSidebarCollapsed)} 
      />
      
      <div className={clsx(
        "flex-1 flex flex-col min-w-0 transition-all duration-300",
        isSidebarCollapsed ? "ml-16" : "ml-sidebar"
      )}>
        <Header isSidebarCollapsed={isSidebarCollapsed} />
        
        {/* Sub-header with actions */}
        <div className="px-8 py-4 border-b border-nexus-outline-variant flex items-center justify-between bg-nexus-surface/20">
          <div className="flex items-center gap-4">
            <h2 className="text-sm font-syne font-bold tracking-widest uppercase">Live Session</h2>
            <div className="flex items-center gap-2 px-2 py-0.5 bg-nexus-primary/10 border border-nexus-primary/20">
              <span className="text-[10px] font-mono text-nexus-primary uppercase">{job_id}</span>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            {state.status === 'done' && (
              <>
                <Button 
                  variant="secondary" 
                  className="!py-1.5 !px-4 text-[10px] gap-2"
                  onClick={() => {
                    reset();
                    window.location.href = '/';
                  }}
                >
                  <Zap size={14} />
                  NEXT EVALUATION
                </Button>
                <Button 
                  variant="primary" 
                  className="!py-1.5 !px-4 text-[10px] gap-2"
                  href={`/evaluate/${job_id}/report`}
                >
                  <FileText size={14} />
                  VIEW FULL REPORT
                </Button>
              </>
            )}
          </div>
        </div>
        
        {/* Three Panel Layout */}
        <div className="flex-1 flex min-h-0">
          
          {/* Panel 1: Pipeline Rail */}
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

          {/* Panel 2: Agent Stream & Live Preview (Center) */}
          <div className="flex-1 flex flex-col min-w-0 border-r border-nexus-outline-variant bg-nexus-surface/5 overflow-hidden">
            {/* Live Simulation View - Now with flex-1 and scroll support */}
            <div className="flex-[0.6] min-h-[300px] p-4 border-b border-nexus-outline-variant bg-nexus-bg/50 overflow-hidden flex flex-col">
              <LivePreviewPanel />
            </div>
            
            <div className="flex-[0.4] min-h-[200px] flex flex-col">
              <AgentStream 
                logs={state.logs}
                isRunning={isRunning}
                activeAgents={state.activeAgents}
              />
            </div>
          </div>

          {/* Panel 3: Output Tabs (Right) - Increased width from 400px to 500px for better diff viewing */}
          <div className="w-[500px] shrink-0 xl:w-[600px] transition-all duration-300">
            <OutputTabs 
              issues={state.issues}
              patches={state.patches}
              results={state.results}
              sessionId={state.jobId}
              status={state.status}
              reportUrl={state.reportUrl}
              downloadUrl={state.downloadUrl}
              pageFilter={null}
            />
          </div>

        </div>
      </div>
    </div>
  );
}
