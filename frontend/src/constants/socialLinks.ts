import { siBluesky, siDiscord, siMastodon } from 'simple-icons'

/**
 * The LinkedIn mark. `simple-icons` no longer ships it, and Lucide ships no brand icons,
 * so the 24x24 path lives here.
 */
const LINKEDIN_PATH =
  'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z'

/**
 * Project social links shown in the footer, as brand-icon paths on a 24x24 canvas.
 *
 * @property key - Stable key, also the suffix of the `footer.<key>` i18n label.
 * @property href - The profile URL.
 * @property path - The SVG path of the brand mark.
 */
export const SOCIAL_LINKS = [
  { key: 'mastodon', href: 'https://fosstodon.org/@endurain', path: siMastodon.path },
  { key: 'bluesky', href: 'https://bsky.app/profile/endurain.bsky.social', path: siBluesky.path },
  { key: 'discord', href: 'https://discord.gg/6VUjUq2uZR', path: siDiscord.path },
  { key: 'linkedin', href: 'https://www.linkedin.com/company/endurain', path: LINKEDIN_PATH },
] as const
