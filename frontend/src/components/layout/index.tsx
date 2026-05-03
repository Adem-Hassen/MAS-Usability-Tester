'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { LayoutDashboard, FileSearch, BarChart3, Settings, User } from 'lucide-react';
import clsx from 'clsx';
import { usePipeline } from '@/hooks/usePipeline';

const NAV_ITEMS = [
  { label: 'Dashboard', icon: LayoutDashboard, href: '/' },
  { label: 'Evaluations', icon: FileSearch, href: '/evaluations' },
  { label: 'Reports', icon: BarChart3, href: '/reports' },
  { label: 'Settings', icon: Settings, href: '/settings' },
];

export function Sidebar({ isCollapsed, onToggle }: { isCollapsed?: boolean; onToggle?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { reset } = usePipeline();

  const handleNav = (href: string) => {
    if (href === '/') {
      reset();
    }
    router.push(href);
  };

  return (
    <aside className={clsx(
      "h-screen bg-[#0E0F11] border-r border-nexus-outline-variant flex flex-col fixed left-0 top-0 z-50 transition-all duration-300",
      isCollapsed ? "w-16" : "w-sidebar"
    )}>
      {/* Brand */}
      <div 
        className={clsx(
          "h-16 flex items-center border-b border-nexus-outline-variant cursor-pointer overflow-hidden transition-all duration-300",
          isCollapsed ? "px-5" : "px-6 gap-3"
        )} 
        onClick={() => handleNav('/')}
      >
        <div className="w-6 h-6 bg-nexus-primary rounded-none shrink-0" />
        {!isCollapsed && <span className="font-syne font-bold text-lg tracking-tight whitespace-nowrap">NEXUS</span>}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-8 flex flex-col gap-1 overflow-hidden">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <button
              key={item.href}
              onClick={() => handleNav(item.href)}
              title={isCollapsed ? item.label : undefined}
              className={clsx(
                'group flex items-center py-3 text-sm font-medium transition-all relative w-full text-left overflow-hidden',
                isCollapsed ? 'px-0 justify-center' : 'px-6 gap-3',
                isActive ? 'text-nexus-primary' : 'text-nexus-outline hover:text-white'
              )}
            >
              {isActive && (
                <div className="absolute left-0 top-0 w-[2px] h-full bg-nexus-primary shadow-[0_0_8px_rgba(196,192,255,0.6)]" />
              )}
              <item.icon size={18} className={clsx('transition-colors shrink-0', isActive ? 'text-nexus-primary' : 'group-hover:text-white')} />
              {!isCollapsed && <span className="whitespace-nowrap">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Toggle & User */}
      <div className="mt-auto border-t border-nexus-outline-variant">
        <button 
          onClick={onToggle}
          className="w-full flex items-center justify-center py-3 text-nexus-outline hover:text-white border-b border-nexus-outline-variant transition-colors"
        >
          <div className={clsx("transition-transform duration-300", isCollapsed ? "rotate-180" : "rotate-0")}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
          </div>
        </button>

        <div className={clsx(
          "flex items-center overflow-hidden transition-all duration-300",
          isCollapsed ? "p-4 justify-center" : "p-6 gap-3"
        )}>
          <div className="w-8 h-8 rounded-full bg-nexus-surface-variant flex items-center justify-center border border-nexus-outline-variant shrink-0">
            <User size={16} className="text-nexus-outline" />
          </div>
          {!isCollapsed && (
            <div className="flex flex-col min-w-0">
              <span className="text-sm font-bold truncate">Alex Chen</span>
              <span className="text-[10px] text-nexus-outline uppercase font-bold tracking-wider">Lead Architect</span>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

export function Header({ isSidebarCollapsed }: { isSidebarCollapsed?: boolean }) {
  const router = useRouter();
  const { reset } = usePipeline();

  const handleNew = () => {
    reset();
    router.push('/');
  };

  return (
    <header className={clsx(
      "h-16 border-b border-nexus-outline-variant bg-nexus-bg/80 backdrop-blur-md flex items-center justify-between px-8 sticky top-0 z-40 transition-all duration-300",
      isSidebarCollapsed ? "ml-16" : "ml-sidebar"
    )}>
      {/* Search */}
      <div className="flex items-center gap-3 bg-nexus-surface-variant px-4 py-2 border border-nexus-outline-variant w-96">
        <div className="w-3 h-3 border-2 border-nexus-outline rounded-full" />
        <input 
          type="text" 
          placeholder="Search components, audits, or agents..." 
          className="bg-transparent border-none outline-none text-sm w-full placeholder:text-nexus-outline/60"
        />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-6">
        <button className="text-nexus-outline hover:text-white relative">
          <div className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 bg-nexus-error rounded-full border-2 border-nexus-bg" />
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>
        </button>
        <button 
          onClick={handleNew}
          className="nexus-button-primary !py-1.5 text-xs"
        >
          + NEW EVALUATION
        </button>
      </div>
    </header>
  );
}
