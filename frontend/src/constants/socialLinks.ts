/**
 * Project community links shown in the footer.
 *
 * @property key - Stable key, also the suffix of the `footer.<key>` i18n label.
 * @property label - The network's brand name, shown as the link text.
 * @property href - The profile URL.
 */
export const SOCIAL_LINKS = [
  { key: 'discord', label: 'Discord', href: 'https://discord.gg/6VUjUq2uZR' },
  { key: 'mastodon', label: 'Mastodon', href: 'https://fosstodon.org/@endurain' },
  { key: 'bluesky', label: 'Bluesky', href: 'https://bsky.app/profile/endurain.bsky.social' },
  { key: 'linkedin', label: 'LinkedIn', href: 'https://www.linkedin.com/company/endurain' },
] as const
