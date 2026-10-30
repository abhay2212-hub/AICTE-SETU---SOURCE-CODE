// Owner: Dev D
// Inline stroke icons for the landing page (24px grid, currentColor).
import type { ReactNode } from 'react'

function Icon({ children, className = 'h-6 w-6' }: { children: ReactNode; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

export function BuildingIcon() {
  return (
    <Icon>
      <path d="M3 21h18M5 21V9l7-5 7 5v12M9 21v-6h6v6M9 11h.01M15 11h.01" />
    </Icon>
  )
}

export function ChartIcon() {
  return (
    <Icon>
      <path d="M3 3v18h18M7 15l4-4 3 3 5-6" />
      <circle cx="19" cy="8" r="1.2" />
    </Icon>
  )
}

export function CapIcon() {
  return (
    <Icon>
      <path d="M2 9l10-5 10 5-10 5L2 9z" />
      <path d="M6 11v5c0 1.5 2.7 3 6 3s6-1.5 6-3v-5M22 9v6" />
    </Icon>
  )
}

export function QrCheckIcon() {
  return (
    <Icon>
      <path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4z" />
      <path d="M14 17l2.5 2.5L21 15" />
    </Icon>
  )
}

export function MaskIcon() {
  return (
    <Icon>
      <path d="M3 3l18 18" />
      <path d="M10.6 5.1A10.4 10.4 0 0 1 12 5c5 0 9 4.5 10 7a12.6 12.6 0 0 1-3.2 4.3M6.6 6.6C4.3 8 2.7 10.1 2 12c1 2.5 5 7 10 7 1.6 0 3.1-.5 4.4-1.2" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    </Icon>
  )
}

export function ShieldIcon() {
  return (
    <Icon>
      <path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z" />
      <path d="M8.5 12l2.5 2.5 4.5-5" />
    </Icon>
  )
}

export function LinkLockIcon() {
  return (
    <Icon>
      <path d="M10 14a4 4 0 0 1 0-5.7l2.3-2.3a4 4 0 0 1 5.7 5.7l-1.2 1.2" />
      <path d="M8.4 10.4 7.2 11.6a4 4 0 0 0 4.3 6.6" />
      <rect x="14" y="16" width="7" height="5" rx="1" />
      <path d="M15.5 16v-1.5a2 2 0 0 1 4 0V16" />
    </Icon>
  )
}

export function ArrowIcon() {
  return (
    <Icon className="h-4 w-4">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </Icon>
  )
}
