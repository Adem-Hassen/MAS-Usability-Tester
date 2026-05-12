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
import { ResizeHandle } from '@/components/layout/ResizeHandle';
import { useResizePanel } from '@/hooks/useResizePanel';

const RAIL_KEY = 'nexus:rail-width';
const RIGHT_KEY = 'nexus:right-width';
const LOGS_KEY = 'nexus:logs-height';

function readSize(key: string, fallback: number) {
  if (typeof window === 'undefined') return fallback;
  const v = localStorage.getItem(key);
  return v ? parseInt(v, 10) : fallback;
}

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

export default function EvaluatePage() {
  const { job_id } = useParams();
  const { state, fetchResults, connect, reset } = usePipeline();
  const [isSidebarCollapsed, setIsSidebarCollapsed] = React.useState(false);
  const isRunning = state.status === 'running' || state.status === 'queued';

  const [vpW, setVpW] = React.useState(typeof window !== 'undefined' ? window.innerWidth : 1400);
  const [vpH, setVpH] = React.useState(typeof window !== 'undefined' ? window.innerHeight : 900);

  useEffect(() => {
    const onResize = () => { setVpW(window.innerWidth); setVpH(window.innerHeight); };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Rail: handle on its RIGHT edge → drag right = rail bigger → NO invert
  const rail = useResizePanel({
    direction: 'horizontal',
    initialSize: clamp(readSize(RAIL_KEY, 256), 200, vpW * 0.35),
    minSize: 200,
    maxSize: vpW * 0.35,
    onResize: (s) => localStorage.setItem(RAIL_KEY, String(s)),
  });

  // Right: handle on its LEFT edge → drag left = right bigger → invert
  const right = useResizePanel({
    direction: 'horizontal',
    initialSize: clamp(readSize(RIGHT_KEY, 520), 360, vpW * 0.45),
    minSize: 360,
    maxSize: vpW * 0.45,
    invert: true,
    onResize: (s) => localStorage.setItem(RIGHT_KEY, String(s)),
  });

  // Logs: handle on its TOP edge → drag UP = logs bigger → invert
  const logs = useResizePanel({
    direction: 'vertical',
    initialSize: clamp(readSize(LOGS_KEY, 300), 180, vpH * 0.5),
    minSize: 180,
    maxSize: vpH * 0.5,
    invert: true,
    onResize: (s) => localStorage.setItem(LOGS_KEY, String(s)),
  });

  // Clamp on window shrink
  useEffect(() => {
    rail.setSize((s) => clamp(s, 200, vpW * 0.35));
    right.setSize((s) => clamp(s, 360, vpW * 0.45));
    logs.setSize((s) => clamp(s, 180, vpH * 0.5));
  }, [vpW, vpH]);

  useEffect(() => {
    if (job_id && typeof job_id === 'string') connect(job_id);
  }, [job_id, connect]);

  useEffect(() => {
    if (state.status === 'done' && !state.results) fetchResults();
  }, [state.status, state.results, fetchResults]);

  useEffect(() => {
    if (state.status !== 'done' || state.results) return;
    const iv = setInterval(() => fetchResults(), 5000);
    return () => clearInterval(iv);
  }, [state.status, state.results, fetchResults]);

  return (
    <div className="flex h-screen bg-nexus-bg font-sans text-white overflow-hidden">
      <Sidebar
        isCollapsed={isSidebarCollapsed}
        onToggle={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
      />

      <div className={clsx(
        'flex-1 flex flex-col min-w-0 transition-all duration-300',
        isSidebarCollapsed ? 'ml-16' : 'ml-sidebar'
      )}>
        <Header isSidebarCollapsed={isSidebarCollapsed} />

        {/* Sub-header */}
        <div className="px-8 py-4 border-b border-nexus-outline-variant flex items-center justify-between bg-nexus-surface/20 shrink-0">
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
                  onClick={() => { reset(); window.location.href = '/'; }}
                >
                  <Zap size={14} /> NEXT EVALUATION
                </Button>
                <Button
                  variant="primary"
                  className="!py-1.5 !px-4 text-[10px] gap-2"
                  href={`/evaluate/${job_id}/report`}
                >
                  <FileText size={14} /> VIEW FULL REPORT
                </Button>
              </>
            )}
          </div>
        </div>

        {/* Main workspace */}
        <div className="flex-1 flex min-h-0 overflow-hidden">

          {/* Left: Pipeline Rail */}
          <div
            className="shrink-0 flex flex-col bg-[#0E0F11] border-r border-nexus-outline-variant overflow-hidden"
            style={{ width: rail.size }}
          >
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
          </div>

          <ResizeHandle direction="horizontal" onMouseDown={rail.handleMouseDown} />

          {/* Center: Preview (flex) above, Logs (fixed) below */}
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

            {/* Top: Preview — fills whatever space is left */}
            <div className="flex-1 flex flex-col overflow-hidden">
              <LivePreviewPanel />
            </div>

            <ResizeHandle direction="vertical" onMouseDown={logs.handleMouseDown} />

            {/* Bottom: Logs — fixed height, handle controls this directly */}
            <div
              className="shrink-0 flex flex-col overflow-hidden"
              style={{ height: logs.size }}
            >
              <AgentStream
                logs={state.logs}
                isRunning={isRunning}
                activeAgents={state.activeAgents}
              />
            </div>
          </div>

          <ResizeHandle direction="horizontal" onMouseDown={right.handleMouseDown} />

          {/* Right: Output Tabs */}
          <div
            className="shrink-0 flex flex-col bg-[#0E0F11] border-l border-nexus-outline-variant overflow-hidden"
            style={{ width: right.size }}
          >
            <OutputTabs
              issues={state.issues}
              patches={state.patches}
              results={state.results}
              sessionId={state.jobId}
              status={state.status}
              reportUrl={state.reportUrl}
              downloadUrl={state.downloadUrl}
              pageFilter={null}
              onFetchResults={fetchResults}
            />
          </div>

        </div>
      </div>
    </div>
  );
}
