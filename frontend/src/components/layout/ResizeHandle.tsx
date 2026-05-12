'use client';

import React from 'react';
import clsx from 'clsx';

interface ResizeHandleProps {
  direction: 'horizontal' | 'vertical';
  onMouseDown: (e: React.MouseEvent) => void;
}

/**
 * Minimal resize handle — thin line that lights up on hover.
 */
export function ResizeHandle({ direction, onMouseDown }: ResizeHandleProps) {
  const isHorizontal = direction === 'horizontal';

  return (
    <div
      onMouseDown={onMouseDown}
      className={clsx(
        'shrink-0 relative z-50',
        isHorizontal
          ? 'w-1 cursor-col-resize hover:bg-nexus-primary/30'
          : 'h-1 cursor-row-resize hover:bg-nexus-primary/30'
      )}
      style={{ backgroundColor: 'rgba(255,255,255,0.03)' }}
    />
  );
}
