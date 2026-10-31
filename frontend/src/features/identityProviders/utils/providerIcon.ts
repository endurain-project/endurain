import { PROVIDER_CUSTOM_LOGO_MAP } from '@/constants/ssoLogos'
import { getApiBaseUrl } from '@/services/runtime'

/** Provider icon keys that ship with a bundled logo asset. */
export const BUILTIN_PROVIDER_ICONS = [
  'authelia',
  'authentik',
  'casdoor',
  'keycloak',
  'pocketid',
] as const

export type BuiltinProviderIcon = (typeof BUILTIN_PROVIDER_ICONS)[number]

/** The sentinel icon option meaning "upload an image to Endurain". */
export const UPLOADED_ICON = 'uploaded'

/** Image types the backend accepts for an uploaded icon. */
export const ICON_ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']

/** Largest uploaded icon the backend accepts, in bytes. */
export const ICON_MAX_BYTES = 1024 * 1024

/** Where a provider's icon is stored, so an uploaded icon can be addressed. */
export interface ProviderIconSource {
  /** The provider slug the uploaded icon is served under. */
  slug: string | null | undefined
  /** Whether an uploaded image is shown instead of the stored icon. */
  iconUploaded: boolean
  /** The provider version, which changes when the image is replaced so the browser refetches it. */
  version?: number
}

/**
 * Narrows an icon value to one of the built-in keys.
 *
 * @param icon - The provider's stored icon value.
 * @returns Whether the icon is a known built-in key.
 */
export function isBuiltinProviderIcon(
  icon: string | null | undefined,
): icon is BuiltinProviderIcon {
  return Boolean(icon) && (BUILTIN_PROVIDER_ICONS as readonly string[]).includes(icon as string)
}

/**
 * Resolves a displayable logo source for a provider icon: the uploaded image
 * when one is stored, the bundled asset for a built-in key, or `null` when none
 * is set.
 *
 * @param icon - The provider's stored icon value (key or URL).
 * @param source - The provider slug and whether an uploaded image replaces `icon`.
 * @returns A logo `src`, or `null` to fall back to a generic icon.
 */
export function resolveProviderLogo(
  icon: string | null | undefined,
  source?: ProviderIconSource,
): string | null {
  if (source?.iconUploaded && source.slug) {
    const url = `${getApiBaseUrl()}/public/idp/${encodeURIComponent(source.slug)}/icon`
    return source.version === undefined ? url : `${url}?v=${source.version}`
  }
  return isBuiltinProviderIcon(icon) ? (PROVIDER_CUSTOM_LOGO_MAP[icon] ?? null) : null
}
