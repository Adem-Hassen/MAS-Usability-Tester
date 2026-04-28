'use client';

import React, { useState, useEffect } from 'react';
import { Sidebar, Header } from '@/components/layout';
import { SectionLabel, Card, Badge, Button } from '@/components/ui';
import { BarChart3, ArrowRight, Download, FileText, Search } from 'lucide-react';
import { getHistory } from '@/lib/api';
import { useRouter } from 'next/navigation';
import clsx from 'clsx';

export default function ReportsPage() {
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
              <h1 className="text-3xl font-syne font-bold tracking-tight">EVALUATION REPORTS</h1>
              <span className="text-nexus-outline font-mono text-sm">/ Archive</span>
            </div>
          </div>

          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <SectionLabel className="mb-0">All Past Audits</SectionLabel>
              <div className="flex items-center gap-2 bg-nexus-surface border border-nexus-outline-variant px-3 py-1.5">
                <Search size={14} className="text-nexus-outline" />
                <input 
                  type="text" 
                  placeholder="Filter by Job ID..." 
                  className="bg-transparent border-none outline-none text-xs w-48 placeholder:text-nexus-outline/40"
                />
              </div>
            </div>

            <Card variant="elevated" className="p-0 overflow-hidden">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b border-nexus-outline-variant bg-nexus-surface-variant/50">
                    <th className="px-6 py-4 font-mono text-[10px] font-bold uppercase tracking-widest text-nexus-outline">Job Identifier</th>
                    <th className="px-6 py-4 font-mono text-[10px] font-bold uppercase tracking-widest text-nexus-outline">Final Status</th>
                    <th className="px-6 py-4 font-mono text-[10px] font-bold uppercase tracking-widest text-nexus-outline">Health</th>
                    <th className="px-6 py-4 font-mono text-[10px] font-bold uppercase tracking-widest text-nexus-outline">Completed</th>
                    <th className="px-6 py-4 font-mono text-[10px] font-bold uppercase tracking-widest text-nexus-outline text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-nexus-outline-variant">
                  {loading ? (
                    <tr>
                      <td colSpan={5} className="px-6 py-12 text-center text-nexus-outline animate-pulse uppercase text-[10px] font-bold tracking-widest">
                        Loading report archive...
                      </td>
                    </tr>
                  ) : history.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-6 py-12 text-center text-nexus-outline uppercase text-[10px] font-bold tracking-widest">
                        No reports found.
                      </td>
                    </tr>
                  ) : (
                    history.map((row, i) => (
                      <tr 
                        key={i} 
                        className="hover:bg-nexus-surface-variant/30 transition-colors cursor-pointer group"
                        onClick={() => router.push(`/evaluate/${row.job_id}/report`)}
                      >
                        <td className="px-6 py-4 font-mono text-xs text-nexus-primary">{row.job_id}</td>
                        <td className="px-6 py-4">
                          <Badge variant={row.status === 'done' ? 'success' : row.status === 'failed' ? 'error' : 'primary'}>
                            {row.status.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-2">
                            <span className="font-syne font-bold">{row.score}%</span>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-nexus-outline font-mono text-xs">
                          {row.created_at ? new Date(row.created_at).toLocaleDateString() : '—'}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button className="p-2 text-nexus-outline hover:text-white transition-colors">
                              <FileText size={16} />
                            </button>
                            <button className="p-2 text-nexus-outline hover:text-white transition-colors">
                              <ArrowRight size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
