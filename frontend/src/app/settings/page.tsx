'use client';

import React, { useState, useEffect } from 'react';
import { Sidebar, Header } from '@/components/layout';
import { SectionLabel, Card, Badge } from '@/components/ui';
import { Shield, Cpu, Sliders } from 'lucide-react';
import { getSettings } from '@/lib/api';
import clsx from 'clsx';

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await getSettings();
        setSettings(data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-screen bg-nexus-bg text-white items-center justify-center font-syne">
        LOADING CONFIGURATION...
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-nexus-bg font-sans text-white">
      <Sidebar />
      
      <main className="flex-1 ml-sidebar flex flex-col">
        <Header />
        
        <div className="p-10 max-w-4xl w-full mx-auto space-y-10">
          <div className="flex items-center justify-between">
            <div className="flex items-baseline gap-4">
              <h1 className="text-3xl font-syne font-bold tracking-tight">SYSTEM SETTINGS</h1>
              <span className="text-nexus-outline font-mono text-sm">/ Configuration</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 border border-nexus-outline-variant bg-nexus-surface-variant/20">
              <Shield size={14} className="text-nexus-secondary" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-nexus-outline">Locked by .env</span>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-8">
            
            {/* Agent Models */}
            <section className="space-y-4">
              <div className="flex items-center gap-3 text-nexus-primary">
                <Cpu size={18} />
                <SectionLabel className="mb-0">Agent Model Engine</SectionLabel>
              </div>
              <Card variant="elevated" className="p-0 overflow-hidden">
                <div className="divide-y divide-nexus-outline-variant">
                  {[
                    { key: 'supervisor_model', label: 'Supervisor Agent', desc: 'Batch analysis and strategy' },
                    { key: 'persona_model', label: 'Persona Agents', desc: 'UI interaction and validation' },
                    { key: 'recommender_model', label: 'Recommender Agent', desc: 'Patch proposal and logic' },
                  ].map((item) => (
                    <div key={item.key} className="p-6 flex items-center justify-between hover:bg-nexus-surface-variant/20 transition-colors">
                      <div className="space-y-1">
                        <div className="text-sm font-bold uppercase tracking-wider">{item.label}</div>
                        <div className="text-xs text-nexus-outline">{item.desc}</div>
                      </div>
                      <div className="bg-nexus-surface border border-nexus-outline-variant text-[10px] font-mono px-3 py-1.5 text-nexus-primary uppercase font-bold">
                        {settings[item.key]}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </section>

            {/* Performance & Logic */}
            <section className="space-y-4">
              <div className="flex items-center gap-3 text-nexus-secondary">
                <Sliders size={18} />
                <SectionLabel className="mb-0">Simulation Parameters</SectionLabel>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <Card variant="elevated" className="space-y-4">
                  <div className="text-xs font-bold uppercase tracking-wider">Persona Density</div>
                  <div className="flex items-center justify-between">
                    <div className="flex-1 h-1.5 bg-nexus-surface-variant relative overflow-hidden">
                      <div 
                        className="absolute h-full bg-nexus-secondary" 
                        style={{ width: `${(settings.max_personas / 10) * 100}%` }} 
                      />
                    </div>
                    <span className="ml-4 font-mono text-lg font-bold text-nexus-secondary">{settings.max_personas}</span>
                  </div>
                  <p className="text-[10px] text-nexus-outline">Number of unique persona agents spawned per page audit.</p>
                </Card>

                <Card variant="elevated" className="space-y-4">
                  <div className="text-xs font-bold uppercase tracking-wider">Step Limit</div>
                  <div className="flex items-center justify-between">
                    <div className="flex-1 h-1.5 bg-nexus-surface-variant relative overflow-hidden">
                      <div 
                        className="absolute h-full bg-nexus-primary" 
                        style={{ width: `${(settings.max_steps / 30) * 100}%` }} 
                      />
                    </div>
                    <span className="ml-4 font-mono text-lg font-bold text-nexus-primary">{settings.max_steps}</span>
                  </div>
                  <p className="text-[10px] text-nexus-outline">Maximum interaction steps allowed per persona simulation.</p>
                </Card>
              </div>
            </section>

            {/* API Status */}
            <section className="space-y-4">
              <div className="flex items-center gap-3 text-nexus-tertiary">
                <Shield size={18} />
                <SectionLabel className="mb-0">Security & Access</SectionLabel>
              </div>
              <Card variant="elevated" className="p-6 space-y-4">
                <div className="flex items-center justify-between p-4 bg-black/20 border border-nexus-outline-variant">
                  <div className="flex items-center gap-3">
                    <div className={clsx("w-2 h-2 rounded-full", settings.has_supervisor_key ? "bg-nexus-secondary" : "bg-nexus-error")} />
                    <span className="text-xs font-bold uppercase tracking-widest">Supervisor API Status</span>
                  </div>
                  <Badge variant={settings.has_supervisor_key ? "success" : "error"}>
                    {settings.has_supervisor_key ? "ACTIVE" : "MISSING"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between p-4 bg-black/20 border border-nexus-outline-variant">
                  <div className="flex items-center gap-3">
                    <div className={clsx("w-2 h-2 rounded-full", settings.has_persona_key ? "bg-nexus-secondary" : "bg-nexus-error")} />
                    <span className="text-xs font-bold uppercase tracking-widest">Persona API Status</span>
                  </div>
                  <Badge variant={settings.has_persona_key ? "success" : "error"}>
                    {settings.has_persona_key ? "ACTIVE" : "MISSING"}
                  </Badge>
                </div>
                <p className="text-[10px] text-nexus-outline italic text-center pt-2">
                  System configuration is locked to .env parameters to ensure environment consistency.
                </p>
              </Card>
            </section>

          </div>
        </div>
      </main>
    </div>
  );
}
