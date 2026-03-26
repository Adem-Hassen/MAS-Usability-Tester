'use client';

// src/components/preview/HtmlPreview.tsx
// Renders HTML in a sandboxed iframe with a toolbar for toggling original/fixed.

import { useState, useRef, useEffect } from 'react';
import clsx from 'clsx';

interface HtmlPreviewProps {
  original:     string;
  fixed:        string;
  filename?:    string;
  fixedFileUrl?: string;
}

export default function HtmlPreview({
  original, fixed, filename, fixedFileUrl
}: HtmlPreviewProps) {
  const [showing, setShowing]   = useState<'fixed' | 'original'>('fixed');
  const [loading, setLoading]   = useState(true);
  const [height, setHeight]     = useState(480);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const html = showing === 'fixed' ? fixed : original;

  // Inject accessibility highlight overlay into fixed HTML
  const injectHighlights = (src: string): string => {
    if (showing === 'original') return src;
    const banner = `
<style>
  .__nexus-fixed {
    outline: 2px solid rgba(74,154,106,0.7) !important;
    outline-offset: 2px !important;
    position: relative !important;
  }
  .__nexus-fixed::after {
    content: '✓ fixed';
    position: absolute;
    top: -18px;
    left: 0;
    background: rgba(74,154,106,0.9);
    color: #fff;
    font-size: 9px;
    font-family: monospace;
    padding: 1px 5px;
    border-radius: 3px;
    pointer-events: none;
    z-index: 9999;
    white-space: nowrap;
  }
  body { margin: 0 !important; }
</style>
<!-- Nexus Accessibility Fixes Applied -->
`;
    return src.replace(/<head>/i, `<head>${banner}`);
  };

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    setLoading(true);
    const blob = new Blob([injectHighlights(html)], { type: 'text/html' });
    const url  = URL.createObjectURL(blob);
    iframe.src = url;
    const onLoad = () => {
      setLoading(false);
      try {
        const h = iframe.contentDocument?.body?.scrollHeight;
        if (h && h > 100) setHeight(Math.min(h + 40, 720));
      } catch {}
    };
    iframe.addEventListener('load', onLoad);
    return () => {
      URL.revokeObjectURL(url);
      iframe.removeEventListener('load', onLoad);
    };
  }, [html, showing]);

  return (
    <div className="rounded-xl border overflow-hidden"
         style={{ background: 'var(--bg2)', borderColor: 'var(--border)' }}>

      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b"
           style={{ background: 'var(--bg3)', borderColor: 'var(--border)' }}>
        {filename && (
          <span className="text-xs font-mono truncate max-w-[200px]"
                style={{ color: 'var(--amber)' }}>
            {filename}
          </span>
        )}

        <div className="ml-auto flex items-center gap-2">
          {/* Toggle */}
          <div className="flex rounded overflow-hidden border" style={{ borderColor: 'var(--border)' }}>
            {(['fixed', 'original'] as const).map(v => (
              <button
                key={v}
                onClick={() => setShowing(v)}
                className={clsx(
                  'text-xs px-3 py-1 capitalize transition-colors',
                  showing === v ? 'bg-amber-400/15 text-amber-400' : 'text-zinc-500 hover:text-zinc-300'
                )}
              >
                {v === 'fixed' ? '✓ Fixed' : 'Original'}
              </button>
            ))}
          </div>

          {fixedFileUrl && (
            <a
              href={fixedFileUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs px-2.5 py-1 rounded border transition-colors hover:border-amber-400/40 hover:text-amber-400"
              style={{ borderColor: 'var(--border)', color: 'var(--text2)' }}
            >
              Open ↗
            </a>
          )}
        </div>
      </div>

      {/* Badge */}
      {showing === 'fixed' && (
        <div className="px-4 py-2 text-xs flex items-center gap-2 border-b"
             style={{ background: 'rgba(74,154,106,0.07)', borderColor: 'rgba(74,154,106,0.15)', color: 'var(--ok)' }}>
          <span>●</span>
          Elements with green outline have been patched by Nexus
        </div>
      )}

      {/* iframe */}
      <div className="relative" style={{ height }}>
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10"
               style={{ background: 'var(--bg2)' }}>
            <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text3)' }}>
              <span className="w-4 h-4 border-2 border-zinc-600 border-t-amber-400 rounded-full animate-spin" />
              Rendering…
            </div>
          </div>
        )}
        <iframe
          ref={iframeRef}
          title={`Preview: ${filename ?? 'page'}`}
          sandbox="allow-scripts allow-same-origin"
          className="w-full h-full border-0 bg-white"
          style={{ opacity: loading ? 0 : 1, transition: 'opacity 0.2s' }}
        />
      </div>
    </div>
  );
}
