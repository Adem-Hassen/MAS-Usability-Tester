'use client';

import { useState, useEffect, useRef } from 'react';

/**
 * Smoothly animate a number from its previous value to a new value.
 * Returns the currently displayed (interpolated) number.
 */
export function useAnimatedNumber(
  target: number,
  duration: number = 600
): number {
  const [display, setDisplay] = useState(target);
  const frameRef = useRef<number>(0);
  const startRef = useRef({ value: target, time: 0 });

  useEffect(() => {
    const startValue = display;
    const startTime = performance.now();
    startRef.current = { value: startValue, time: startTime };

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = startValue + (target - startValue) * eased;
      setDisplay(current);

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate);
      }
    };

    frameRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameRef.current);
  }, [target, duration]);

  return Math.round(display);
}
