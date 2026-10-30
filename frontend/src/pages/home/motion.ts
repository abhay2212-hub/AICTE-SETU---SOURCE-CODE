// Owner: Dev D
// Small motion hooks for the landing page. Both honour prefers-reduced-motion.
import { useEffect, useRef, useState } from 'react'

export function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
  )
}

/** Counts from 0 to ``target`` with an ease-out curve once ``target`` is known. */
export function useCountUp(target: number | undefined, duration = 1000): number {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (target === undefined) return
    const span = prefersReducedMotion() ? 0 : duration
    let frame = 0
    let start: number | undefined
    const tick = (now: number) => {
      start ??= now
      const progress = span === 0 ? 1 : Math.min((now - start) / span, 1)
      setValue(Math.round(target * (1 - (1 - progress) ** 3)))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, duration])
  return value
}

/** True once the element has scrolled into view (immediately with reduced motion). */
export function useInView<T extends Element>(): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    const element = ref.current
    if (!element) return
    if (prefersReducedMotion() || typeof IntersectionObserver === 'undefined') {
      const frame = requestAnimationFrame(() => setSeen(true))
      return () => cancelAnimationFrame(frame)
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setSeen(true)
          observer.disconnect()
        }
      },
      { threshold: 0.35 },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return [ref, seen]
}
