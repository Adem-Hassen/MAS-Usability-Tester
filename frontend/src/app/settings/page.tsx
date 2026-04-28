'use client';

import React, { useState, useEffect } from 'react';
import { Sidebar, Header } from '@/components/layout';
import { SectionLabel, Card, Button, Badge } from '@/components/ui';
import { Settings as SettingsIcon, Save, Shield, Cpu, Sliders, CheckCircle2 } from 'lucide-react';
import { getSettings, updateSettings } from '@/lib/api';
import clsx from 'clsx';

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);

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

  const handleSave = async () => {
    setSaving(true);
    setSuccess(false);
    try {
      await updateSettings(settings);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

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
            <Button 
              variant="primary" 
              className="gap-2 min-w-[120px]" 
              onClick={handleSave}
              disabled={saving}
            >
              {success ? <CheckCircle2 size={16} /> : <Save size={16} />}
              {saving ? 'SAVING...' : success ? 'SAVED' : 'SAVE CHANGES'}
            </Button>
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
                      <select 
                        className="bg-nexus-surface border border-nexus-outline-variant text-xs font-mono p-2 focus:border-nexus-primary outline-none"
                        value={settings[item.key]}
                        onChange={(e) => setSettings({ ...settings, [item.key]: e.target.value })}
                        disabled
                      >
                        <option>{settings[item.key]}</option>
                      </select>
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
                    <input 
                      type="range" 
                      min="1" 
                      max="10" 
                      value={settings.max_personas}
                      onChange={(e) => setSettings({ ...settings, max_personas: parseInt(e.target.value) })}
                      className="flex-1 accent-nexus-secondary"
                    />
                    <span className="ml-4 font-mono text-lg font-bold text-nexus-secondary">{settings.max_personas}</span>
                  </div>
                  <p className="text-[10px] text-nexus-outline">Number of unique persona agents spawned per page audit.</p>
                </Card>

                <Card variant="elevated" className="space-y-4">
                  <div className="text-xs font-bold uppercase tracking-wider">Step Limit</div>
                  <div className="flex items-center justify-between">
                    <input 
                      type="range" 
                      min="5" 
                      max="30" 
                      value={settings.max_steps}
                      onChange={(e) => setSettings({ ...settings, max_steps: parseInt(e.target.value) })}
                      className="flex-1 accent-nexus-primary"
                    />
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
                <p className="text-[10px] text-nexus-outline italic">API keys are managed via system environment variables for maximum security.</p>
              </Card>
            </section>

          </div>
        </div>
      </main>
    </div>
  );
}
