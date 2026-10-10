import {
  FolderInput,
  KeyRound,
  Layers,
  Plug,
  ScrollText,
  ServerCog,
  ShieldCheck,
  Target,
  User,
  Users,
  type LucideIcon,
} from '@lucide/vue'

/**
 * One entry in the settings sidebar. Each zone is a nested child route under
 * `/settings`, so the sidebar, the index redirect, and the route table all read
 * from this single list.
 *
 * @property name - Target child route name.
 * @property labelKey - i18n key for the sidebar label.
 * @property icon - Lucide icon component.
 * @property adminOnly - Whether the zone is restricted to administrators.
 */
export interface SettingsZone {
  name: string
  labelKey: string
  icon: LucideIcon
  adminOnly: boolean
}

/**
 * The settings zones, in sidebar order. New zones (profile, security, …) are
 * added here and as matching child routes; the sidebar and redirect pick them
 * up automatically.
 */
export const SETTINGS_ZONES: readonly SettingsZone[] = [
  { name: 'settings-users', labelKey: 'settings.nav.users', icon: Users, adminOnly: true },
  { name: 'settings-idp', labelKey: 'settings.nav.idp', icon: KeyRound, adminOnly: true },
  { name: 'settings-server', labelKey: 'settings.nav.server', icon: ServerCog, adminOnly: true },
  {
    name: 'settings-event-log',
    labelKey: 'settings.nav.eventLog',
    icon: ScrollText,
    adminOnly: true,
  },
  {
    name: 'settings-jobs',
    labelKey: 'settings.nav.jobs',
    icon: Layers,
    adminOnly: true,
  },
  { name: 'settings-profile', labelKey: 'settings.nav.profile', icon: User, adminOnly: false },
  { name: 'settings-goals', labelKey: 'settings.nav.goals', icon: Target, adminOnly: false },
  {
    name: 'settings-security',
    labelKey: 'settings.nav.security',
    icon: ShieldCheck,
    adminOnly: false,
  },
  {
    name: 'settings-integrations',
    labelKey: 'settings.nav.integrations',
    icon: Plug,
    adminOnly: false,
  },
  {
    name: 'settings-import',
    labelKey: 'settings.nav.import',
    icon: FolderInput,
    adminOnly: false,
  },
]

/**
 * Returns the zones a user may open, filtering admin-only zones for non-admins.
 *
 * @param isAdmin - Whether the current user is an administrator.
 * @returns The accessible settings zones, in sidebar order.
 */
export function accessibleSettingsZones(isAdmin: boolean): SettingsZone[] {
  return SETTINGS_ZONES.filter((zone) => !zone.adminOnly || isAdmin)
}
