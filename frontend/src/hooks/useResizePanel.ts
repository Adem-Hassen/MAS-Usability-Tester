'use client';

import { useCallback, useRef, useState } from 'react';

interface UseResizePanelOptions {
  direction: 'horizontal' | 'vertical';
  initialSize: number;
  minSize?: number;
  maxSize?: number;
  invert?: boolean;
  onResize?: (size: number) => void;
}

export function useResizePanel(options: UseResizePanelOptions) {
  const { direction, initialSize, minSize = 150, maxSize = Infinity, invert = false, onResize } = options;
  const [size, setSize] = useState(initialSize);
  const isDragging = useRef(false);
  const startPos = useRef(0);
  const startSize = useRef(initialSize);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    isDragging.current = true;
    startPos.current = direction === 'horizontal' ? e.clientX : e.clientY;
    startSize.current = size;

    document.body.style.cursor = direction === 'horizontal' ? 'col-resize' : 'row-resize';
    document.body.style.userSelect = 'none';

    const handleMove = (ev: MouseEvent) => {
      if (!isDragging.current) return;
      const current = direction === 'horizontal' ? ev.clientX : ev.clientY;
      const delta = current - startPos.current;
      const raw = invert ? startSize.current - delta : startSize.current + delta;
      const next = Math.max(minSize, Math.min(maxSize, raw));
      setSize(next);
      onResize?.(next);
    };

    const handleUp = () => {
      isDragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
  }, [direction, minSize, maxSize, invert, onResize, size]);

  return { size, setSize, handleMouseDown };
}
