import { apiFetch } from '@/services/http'

/** The GitHub API endpoint for the latest stable release of Endurain. */
const LATEST_RELEASE_URL = 'https://api.github.com/repos/endurain-project/endurain/releases/latest'

/** The GitHub API endpoint listing recent releases (includes pre-releases). */
const RELEASES_LIST_URL =
  'https://api.github.com/repos/endurain-project/endurain/releases?per_page=10'

/** Minimal shape returned by the backend `/about` endpoint. */
export interface AboutResponse {
  name: string
  version: string
}

/** Minimal shape returned by the GitHub releases API. */
interface GitHubRelease {
  tag_name: string
  prerelease: boolean
}

/**
 * Returns `true` when the version string contains a pre-release suffix
 * (e.g. `"0.19.0-beta1"`).
 */
export function isPreRelease(version: string): boolean {
  return version.includes('-')
}

/**
 * Fetches the running backend's version from the `/about` endpoint.
 *
 * @param signal - Optional abort signal forwarded from TanStack Query.
 * @returns The current backend version string (e.g. `"0.20.0"`).
 */
export async function fetchBackendVersion(signal?: AbortSignal): Promise<string> {
  const data = await apiFetch<AboutResponse>('/about', { auth: false, signal })
  const v = data.version
  return v.startsWith('v') ? v.slice(1) : v
}

/**
 * Fetches the latest published release tag from the GitHub repository.
 *
 * The tag is normalised by stripping a leading `v` so it can be compared
 * directly against the version string returned by `/about`.
 *
 * @param signal - Optional abort signal forwarded from TanStack Query.
 * @returns The latest version string (e.g. `"0.21.0"`), or `null` when the
 *   request fails (network offline, rate-limited, etc.) — callers treat `null`
 *   as "update status unknown".
 */
export async function fetchLatestRelease(signal?: AbortSignal): Promise<string | null> {
  try {
    const res = await fetch(LATEST_RELEASE_URL, { signal })
    if (!res.ok) return null
    const data = (await res.json()) as GitHubRelease
    if (data.prerelease) return null
    const tag = data.tag_name ?? ''
    return tag.startsWith('v') ? tag.slice(1) : tag || null
  } catch {
    return null
  }
}

/**
 * Fetches the latest pre-release tag from the GitHub repository.
 *
 * Used to notify users who are already running a pre-release build about a
 * newer beta. Stable users never see this result.
 *
 * @param signal - Optional abort signal forwarded from TanStack Query.
 * @returns The latest pre-release version string (e.g. `"0.19.0-beta2"`), or
 *   `null` when none exists or the request fails.
 */
export async function fetchLatestPreRelease(signal?: AbortSignal): Promise<string | null> {
  try {
    const res = await fetch(RELEASES_LIST_URL, { signal })
    if (!res.ok) return null
    const data = (await res.json()) as GitHubRelease[]
    const found = data.find((r) => r.prerelease)
    if (!found) return null
    const tag = found.tag_name ?? ''
    return tag.startsWith('v') ? tag.slice(1) : tag || null
  } catch {
    return null
  }
}

/**
 * Compares two semver-like version strings, including pre-release suffixes.
 *
 * Numeric segments (`MAJOR.MINOR.PATCH`) are compared first. When all numeric
 * segments are equal, pre-release suffixes are handled following the semver
 * convention: a stable release is greater than any pre-release of the same
 * version (e.g. `0.19.0 > 0.19.0-beta2`). Pre-release identifiers with the
 * same alphabetic prefix are compared by their trailing number
 * (e.g. `0.19.0-beta2 > 0.19.0-beta1`).
 *
 * @param current - The running version (e.g. `"0.19.0-beta1"`).
 * @param latest  - The latest published version (e.g. `"0.19.0-beta2"`).
 * @returns `true` when `latest` is strictly greater than `current`.
 */
export function isNewerVersion(current: string, latest: string): boolean {
  const parsePre = (pre: string): { prefix: string; num: number } => {
    const m = pre.match(/^([a-zA-Z]*)([0-9]*)$/)
    return m ? { prefix: m[1] ?? '', num: m[2] ? parseInt(m[2], 10) : 0 } : { prefix: pre, num: 0 }
  }

  const parse = (v: string): { nums: number[]; pre: string | null } => {
    const parts = v.split('.')
    const nums: number[] = []
    let pre: string | null = null
    for (const part of parts) {
      const dash = part.indexOf('-')
      if (dash !== -1) {
        nums.push(parseInt(part.slice(0, dash), 10))
        pre = part.slice(dash + 1)
      } else {
        nums.push(parseInt(part, 10))
      }
    }
    return { nums, pre }
  }

  const c = parse(current)
  const l = parse(latest)

  for (let i = 0; i < Math.max(c.nums.length, l.nums.length); i++) {
    const cv = c.nums[i] ?? 0
    const lv = l.nums[i] ?? 0
    if (lv > cv) return true
    if (lv < cv) return false
  }

  // Numeric segments are equal — compare pre-release.
  // Stable (null) is greater than any pre-release string.
  if (c.pre === null && l.pre === null) return false
  if (l.pre === null) return true // latest is stable; current is pre-release
  if (c.pre === null) return false // current is stable; latest is pre-release

  // Both have pre-release identifiers.
  const cp = parsePre(c.pre)
  const lp = parsePre(l.pre)
  if (cp.prefix !== lp.prefix) return lp.prefix > cp.prefix
  return lp.num > cp.num
}
