/**
 * An inline <script> that runs while the browser parses the HTML — before the
 * first paint, and before React hydrates.
 *
 * Used for the one thing that genuinely can't wait for React: applying the
 * saved colour theme. Doing it in an effect instead would render the wrong
 * theme for a frame and then snap.
 *
 * The type swap is the documented way to stop React warning about script tags
 * in components: the server emits a real script, the client emits an inert one
 * it will never try to run. suppressHydrationWarning covers that difference.
 *
 * See node_modules/next/dist/docs/01-app/02-guides/preventing-flash-before-hydration.md
 */
export function InlineScript({ html }: { html: string }) {
  return (
    <script
      type={typeof window === 'undefined' ? 'text/javascript' : 'text/plain'}
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
