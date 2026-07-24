'use client'

import { useId } from 'react'

/**
 * The Cognira mark — a rounded tile with the C and the answer bubble cut
 * *out* of it, so whatever is behind shows through. That knockout is why it
 * reads as an app icon rather than a drawing of one.
 *
 * The cutout needs an SVG <mask>, and mask ids are global to the page — so
 * each instance generates its own. Rendering two logos on one screen without
 * this makes the second one silently reuse the first one's mask.
 */
export function Logo({ size = 32, className = '' }: { size?: number; className?: string }) {
  const maskId = `logo-cut-${useId().replace(/:/g, '')}`

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      className={className}
      role="img"
      aria-label="Cognira"
    >
      <defs>
        <mask id={maskId}>
          {/* White keeps, black cuts away */}
          <rect width="48" height="48" fill="#fff" />
          <path
            d="M32.5 16.6a10.4 10.4 0 100 14.8"
            fill="none"
            stroke="#000"
            strokeWidth="5.6"
            strokeLinecap="round"
          />
          <circle cx="24" cy="24" r="3.8" fill="#000" />
        </mask>
      </defs>
      <rect
        x="3"
        y="3"
        width="42"
        height="42"
        rx="13"
        fill="currentColor"
        mask={`url(#${maskId})`}
      />
    </svg>
  )
}

/**
 * Mark plus name, for headers and the sign-in screen.
 *
 * The text is sized off the mark rather than from the type scale — a lockup
 * has to hold its proportions at whatever size it's placed at. 0.8 puts the
 * cap-height close to the height of the tile, which is what makes the two
 * read as one object instead of an icon with a caption next to it.
 */
export function Wordmark({ size = 30, className = '' }: { size?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <Logo size={size} className="text-accent" />
      <span
        className="font-bold tracking-tight text-text leading-none"
        style={{ fontSize: Math.round(size * 0.8) }}
      >
        Cognira
      </span>
    </span>
  )
}
