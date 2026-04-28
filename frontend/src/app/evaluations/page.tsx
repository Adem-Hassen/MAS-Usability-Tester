'use client';

import React, { useState, useEffect } from 'react';
import { Sidebar, Header } from '@/components/layout';
import { SectionLabel, Card, Badge, Button, StatusDot } from '@/components/ui';
import { FileSearch, ArrowRight, Clock, Trash2, Play } from 'lucide-react';
import { getHistory } from '@/lib/api';
import { useRouter } from 'next/navigation';
import clsx from 'clsx';

export default function EvaluationsPage() {
  const router = useRouter();
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await getHistory();
        setHistory(data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="flex min-h-screen bg-nexus-bg font-sans text-white">
      <Sidebar />
      
      <main className="flex-1 ml-sidebar flex flex-col">
        <Header />
        
        <div className="p-10 max-w-6xl w-full mx-auto space-y-10">
          <div className="flex items-center justify-between">
            <div className="flex items-baseline gap-4">
              <h1 className="text-3xl font-syne font-bold tracking-tight">EVALUATION SESSIONS</h1>
              <span className="text-nexus-outline font-mono text-sm">/ Sessions Registry</span>
            </div>
            <Button variant="primary" className="gap-2" onClick={() => router.push('/')}>
              <Play size={16} />
              NEW EVALUATION
            </Button>
          </div>

          <div className="space-y-6">
            <SectionLabel>Active and Past Sessions</SectionLabel>
            
            <div className="grid grid-cols-1 gap-4">
              {loading ? (
                <div className="py-20 text-center text-nexus-outline animate-pulse uppercase text-[10px] font-bold tracking-widest">
                  Loading sessions...
                </div>
              ) : history.length === 0 ? (
                <Card className="py-20 text-center text-nexus-outline border-dashed">
                  NO EVALUATIONS FOUND. START BY UPLOADING YOUR FILES ON THE DASHBOARD.
                </Card>
              ) : (
                history.map((row, i) => (
                  <Card 
                    key={i} 
                    variant="elevated" 
                    className="p-0 overflow-hidden hover:border-nexus-primary/40 transition-colors cursor-pointer group"
                    onClick={() => router.push(`/evaluate/${row.job_id}`)}
                  >
                    <div className="flex items-center p-6 gap-6">
                      <div className="w-12 h-12 bg-nexus-surface border border-nexus-outline-variant flex items-center justify-center text-nexus-primary group-hover:scale-110 transition-transform">
                        <FileSearch size={24} />
                      </div>
                      
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-sm font-bold text-nexus-primary">{row.job_id}</span>
                          <Badge variant={row.status === 'done' ? 'success' : row.status === 'failed' ? 'error' : 'primary'}>
                            {row.status.toUpperCase()}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-4 text-nexus-outline text-[10px] font-bold uppercase tracking-wider">
                          <span className="flex items-center gap-1">
                            <Clock size={12} />
                            {row.created_at ? new Date(row.created_at).toLocaleString() : 'Date Unknown'}
                          </span>
                          <span>•</span>
                          <span>{row.files || 0} Files Audited</span>
                        </div>
                      </div>

                      <div className="flex flex-col items-end gap-2 pr-4">
                        <div className="text-xs font-bold uppercase tracking-widest text-nexus-outline">Health Score</div>
                        <div className="text-2xl font-syne font-bold text-white">{row.score}%</div>
                      </div>

                      <div className="pl-6 border-l border-nexus-outline-variant group-hover:text-nexus-primary transition-colors">
                        <ArrowRight size={24} />
                      </div>
                    </div>
                  </Card>
                ))
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
