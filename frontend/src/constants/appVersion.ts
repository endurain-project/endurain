import { version } from '../../package.json'

/** The app version, read from `package.json` so a release bump cannot leave a screen stale. */
export const APP_VERSION = `v${version}`
