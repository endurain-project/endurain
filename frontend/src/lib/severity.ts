import type { Severity } from '@/types'

/**
 * Maps a {@link Severity} to its token-based border/background/text classes.
 * Shared by the inline `Alert` component and the toast host so both render
 * severities from one source of truth.
 */
export const severityClasses: Record<Severity, string> = {
  info: 'border-info/40 bg-info/10 text-info',
  success: 'border-goal/40 bg-goal/10 text-goal',
  warning: 'border-effort/40 bg-effort/10 text-effort',
  error: 'border-hr/40 bg-hr/10 text-hr',
}

/**
 * Toast variant of {@link severityClasses}. Toasts float over arbitrary page
 * content rather than a known card/surface background, so they need an
 * opaque backing (`bg-popover`) instead of a tinted, translucent one —
 * otherwise whatever is behind the toast shows through and the message
 * becomes hard to read.
 */
export const severityToastClasses: Record<Severity, string> = {
  info: 'border-info/40 bg-popover text-info',
  success: 'border-goal/40 bg-popover text-goal',
  warning: 'border-effort/40 bg-popover text-effort',
  error: 'border-hr/40 bg-popover text-hr',
}
