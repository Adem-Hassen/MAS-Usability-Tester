'use client';

import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { useRouter } from 'next/navigation';
import { usePipeline } from '@/hooks/usePipeline';
import { Sidebar, Header } from '@/components/layout';
import { MetricCard, SectionLabel, Button, Card, Badge, StatusDot } from '@/components/ui';
import { Upload, Play, Clock, ArrowRight, ShieldCheck, AlertCircle, Zap } from 'lucide-react';
import { getHistory } from '@/lib/api';
import clsx from 'clsx';

export default function DashboardPage() {
  const router = useRouter();
  const { upload, state } = usePipeline();
  const [uploading, setUploading] = useState(false);
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    async function load() {
      try {
        const data = await getHistory();
        setHistory(data.slice(0, 10)); // Just the 10 most recent
      } catch (e) {
        console.error(e);
      }
    }
    load();
  }, []);

  const onDrop = useCallback(async (accepted: File[]) => {
    if (!accepted.length) return;
    setUploading(true);
    try {
      const jobId = await upload(accepted);
      // Navigate to evaluation page once job starts
      router.push(`/evaluate/${jobId}`);
    } catch (e) {
      console.error(e);
    } finally {
      setUploading(false);
    }
  }, [upload, router]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'text/html': ['.html'] },
    maxFiles: 5,
    disabled: uploading,
  });

  return (
    <div className="flex min-h-screen bg-nexus-bg font-sans text-white">
      <Sidebar />
      
      <main className="flex-1 ml-sidebar flex flex-col">
        <Header />

        <div className="p-8 max-w-7xl w-full mx-auto space-y-10">
          
          {/* Title Section */}
          <div className="flex items-center justify-between">
            <div className="flex items-baseline gap-4">
              <h1 className="text-3xl font-syne font-bold tracking-tight">GLOBAL HEALTH</h1>
              <span className="text-nexus-outline font-mono text-sm">/ System Overview</span>
            </div>
            <div className="flex items-center gap-2 bg-nexus-secondary/10 border border-nexus-secondary/20 px-3 py-1">
              <StatusDot status="done" className="!w-1.5 !h-1.5" />
              <span className="text-[10px] font-bold text-nexus-secondary uppercase tracking-widest">SYSTEM LIVE</span>
            </div>
          </div>

          {/* Metrics Row */}
          <div className="grid grid-cols-3 gap-6">
            <MetricCard 
              label="Compliance Rate" 
              value="94.2%" 
              variant="secondary"
              trend={{ value: "+2.4%", type: 'positive' }}
              subtext="vs last 30 days"
            />
            <MetricCard 
              label="Critical Issues" 
              value="12" 
              variant="error"
              trend={{ value: "-4", type: 'positive' }}
              subtext="Resolved today"
            />
            <MetricCard 
              label="Avg. Response" 
              value="1.2s" 
              variant="primary"
              subtext="Per Persona Simulation"
            />
          </div>

          {/* Main Actions Section */}
          <div className="grid grid-cols-12 gap-6">
            
            {/* Component Analyzer / Upload Zone */}
            <div className="col-span-8">
              <Card className="h-full flex flex-col">
                <div className="mb-6 flex items-center justify-between">
                  <SectionLabel className="mb-0">Component Analyzer</SectionLabel>
                  <Badge variant="primary" className="!rounded-none">BETA</Badge>
                </div>

                <div 
                  {...getRootProps()}
                  className={clsx(
                    "flex-1 flex flex-col items-center justify-center border-2 border-dashed transition-all duration-300 p-12 text-center group cursor-pointer",
                    isDragActive 
                      ? "border-nexus-primary bg-nexus-primary/5 scale-[1.01]" 
                      : "border-nexus-outline-variant hover:border-nexus-primary/40 hover:bg-nexus-surface-variant"
                  )}
                >
                  <input {...getInputProps()} />
                  <div className="w-16 h-16 bg-nexus-surface-variant border border-nexus-outline-variant flex items-center justify-center mb-6 transition-transform duration-300 group-hover:scale-110">
                    <Upload className={clsx("transition-colors", isDragActive ? "text-nexus-primary" : "text-nexus-outline")} size={32} />
                  </div>
                  <h3 className="text-lg font-syne font-bold mb-2">Drag & Drop Component</h3>
                  <p className="text-sm text-nexus-outline max-w-sm mb-8">
                    Drop  HTML files to start a deep accessibility audit.
                  </p>
                  <Button variant="primary" className="gap-3">
                    {uploading ? "UPLOADING..." : "SELECT FILES"}
                    <ArrowRight size={16} />
                  </Button>
                </div>
              </Card>
            </div>

            {/* Quick Stats / Info */}
            <div className="col-span-4 space-y-6">
              <Card variant="elevated" className="space-y-4">
                <SectionLabel>Real-time Progress</SectionLabel>
                <div className="space-y-6">
                  {[
                    { label: 'UI Analysis', status: 'done', icon: ShieldCheck },
                    { label: 'Persona Simulations', status: 'running', icon: Play },
                    { label: 'Issue Clustering', status: 'idle', icon: AlertCircle },
                    { label: 'Patch Generation', status: 'idle', icon: Zap },
                  ].map((step, i) => (
                    <div key={i} className="flex items-center gap-4">
                      <div className={clsx(
                        "w-8 h-8 flex items-center justify-center border",
                        step.status === 'done' ? "bg-nexus-secondary/10 border-nexus-secondary/20 text-nexus-secondary" :
                        step.status === 'running' ? "bg-nexus-primary/10 border-nexus-primary/20 text-nexus-primary" :
                        "bg-nexus-surface border-nexus-outline-variant text-nexus-outline"
                      )}>
                        <step.icon size={16} />
                      </div>
                      <div className="flex-1">
                        <div className="text-xs font-bold uppercase tracking-wider">{step.label}</div>
                        <div className="text-[10px] text-nexus-outline font-mono">
                          {step.status === 'done' ? 'Completed' : step.status === 'running' ? 'In Progress' : 'Queued'}
                        </div>
                      </div>
                      {step.status === 'running' && <StatusDot status="running" />}
                    </div>
                  ))}
                </div>
              </Card>

              <Card className="bg-nexus-primary/5 border-nexus-primary/20 flex flex-col items-center justify-center p-8 text-center">
                <Clock className="text-nexus-primary mb-4" size={24} />
                <div className="text-sm font-bold uppercase tracking-widest mb-1">Total Uptime</div>
                <div className="text-2xl font-syne font-bold">142:04:12</div>
              </Card>
            </div>

          </div>

          {/* History Table */}
          <div className="space-y-4">
            <SectionLabel>Evaluation History</SectionLabel>
            <div className="border border-nexus-outline-variant bg-nexus-surface">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b border-nexus-outline-variant bg-nexus-surface-variant/50">
                    <th className="px-6 py-4 font-mono text-[10px] font-bold uppercase tracking-widest text-nexus-outline">Project Name</th>
                    <th className="px-6 py-4 font-mono text-[10px] font-bold uppercase tracking-widest text-nexus-outline">Status</th>
                    <th className="px-6 py-4 font-mono text-[10px] font-bold uppercase tracking-widest text-nexus-outline">Health Score</th>
                    <th className="px-6 py-4 font-mono text-[10px] font-bold uppercase tracking-widest text-nexus-outline">Last Run</th>
                    <th className="px-6 py-4 font-mono text-[10px] font-bold uppercase tracking-widest text-nexus-outline text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-nexus-outline-variant">
                  {history.map((row, i) => (
                    <tr 
                      key={i} 
                      className="hover:bg-nexus-surface-variant/30 transition-colors cursor-pointer group"
                      onClick={() => router.push(`/evaluate/${row.job_id}/report`)}
                    >
                      <td className="px-6 py-4 font-mono text-xs">{row.job_id}</td>
                      <td className="px-6 py-4">
                        <Badge variant={row.status === 'done' ? 'success' : row.status === 'failed' ? 'error' : 'primary'}>
                          {row.status === 'done' ? 'COMPLIANT' : row.status === 'failed' ? 'CRITICAL' : row.status.toUpperCase()}
                        </Badge>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-24 h-1.5 bg-nexus-surface-variant rounded-none overflow-hidden">
                            <div 
                              className={clsx(
                                "h-full",
                                row.score > 90 ? "bg-nexus-secondary" : row.score > 70 ? "bg-nexus-tertiary" : "bg-nexus-error"
                              )} 
                              style={{ width: `${row.score}%` }} 
                            />
                          </div>
                          <span className="font-mono text-xs font-bold">{row.score}%</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-nexus-outline font-mono text-xs">
                        {row.created_at ? new Date(row.created_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button className="text-nexus-outline hover:text-nexus-primary transition-colors">
                          <ArrowRight size={18} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

        </div>
      </main>
    </div>
  );
}
