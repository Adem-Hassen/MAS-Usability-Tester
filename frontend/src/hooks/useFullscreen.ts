'use client';

import { useState, useCallback, useEffect } from 'react';

interface FullscreenState {
  isFullscreen: boolean;
  enter: () => void;
  exit: () => void;
  toggle: () => void;
}

/**
 * Hook for managing fullscreen state on a specific DOM element.
 */
export function useFullscreen(ref: React.RefObject<HTMLElement | null> | React.MutableRefObject<HTMLElement | null>): FullscreenState {
  const [isFullscreen, setIsFullscreen] = useState(false);

  const enter = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    if (el.requestFullscreen) {
      el.requestFullscreen().catch(() => {});
    } else if ((el as any).webkitRequestFullscreen) {
      (el as any).webkitRequestFullscreen();
    }
  }, [ref]);

  const exit = useCallback(() => {
    if (document.exitFullscreen) {
      document.exitFullscreen().catch(() => {});
    } else if ((document as any).webkitExitFullscreen) {
      (document as any).webkitExitFullscreen();
    }
  }, []);

  const toggle = useCallback(() => {
    if (isFullscreen) exit();
    else enter();
  }, [isFullscreen, enter, exit]);

  useEffect(() => {
    const onChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', onChange);
    document.addEventListener('webkitfullscreenchange', onChange);
    return () => {
      document.removeEventListener('fullscreenchange', onChange);
      document.removeEventListener('webkitfullscreenchange', onChange);
    };
  }, []);

  return { isFullscreen, enter, exit, toggle };
}
