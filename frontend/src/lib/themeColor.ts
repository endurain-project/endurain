/**
 * Resolves an Endurain design-token colour (declared in the `@theme` block of
 * `src/assets/main.css`) to a concrete colour string for canvas/JS contexts —
 * Chart.js and similar render to a `<canvas>` and cannot consume `var(--…)`.
 *
 * Reading the live computed value keeps `main.css` the single source of truth,
 * so charts stay in sync with the design tokens instead of duplicating their
 * hex values. A bundled fallback is returned when no document/stylesheet is
 * available (SSR, unit tests).
 */

/** Design-token colours that may be resolved for canvas/JS rendering. */
export type ThemeColorToken =
  | '--color-brand'
  | '--color-brand-mid'
  | '--color-effort'
  | '--color-hr'
  | '--color-info'
  | '--color-goal'
  | '--color-popover'
  | '--color-popover-foreground'
  | '--color-border'

/**
 * Bundled fallbacks mirroring `main.css`, used when the live stylesheet is not
 * available (SSR, unit tests). The single place these hex values are repeated.
 */
const TOKEN_FALLBACKS: Record<ThemeColorToken, string> = {
  '--color-brand': '#1d9e75',
  '--color-brand-mid': '#0f6e56',
  '--color-effort': '#ef9f27',
  '--color-hr': '#e24b4a',
  '--color-info': '#378add',
  '--color-goal': '#639922',
  '--color-popover': '#ffffff',
  '--color-popover-foreground': '#2c2c2a',
  '--color-border': 'rgba(0, 0, 0, 0.08)',
}

/**
 * Reads a custom property, following one `@theme` alias such as
 * `var(--popover)`. The alias target is what `.dark` overrides.
 */
function readToken(name: string, depth = 0): string {
  if (depth > 4) {
    return ''
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const alias = /^var\(\s*(--[\w-]+)\s*\)$/.exec(value)
  if (alias?.[1]) {
    return readToken(alias[1], depth + 1)
  }
  return value
}

/**
 * Resolves a design-token colour to its concrete value.
 *
 * @param token - The CSS custom property name, e.g. `--color-brand-mid`.
 * @returns The live computed token value, or the bundled fallback when no
 *   document/stylesheet is available.
 */
export function themeColor(token: ThemeColorToken): string {
  if (typeof document !== 'undefined') {
    const resolved = readToken(token)
    if (resolved) {
      return resolved
    }
  }
  return TOKEN_FALLBACKS[token]
}
