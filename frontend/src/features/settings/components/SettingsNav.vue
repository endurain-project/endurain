<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Check, ChevronDown, Menu } from '@lucide/vue'

import type { SettingsZone } from '@/features/settings/settingsNav'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useIsAdmin } from '@/features/auth/composables/useCurrentUser'
import { accessibleSettingsZones } from '@/features/settings/settingsNav'

/**
 * Settings sidebar. Lists the zones the current user can open (admin-only zones
 * are hidden from non-admins) and highlights the active one. Zones are split
 * into an "account" group and an "administration" group, separating personal
 * from admin settings, with group headings shown
 * only when both groups are present (i.e. for admins). The list is driven by
 * the shared {@link accessibleSettingsZones} config so it stays in sync with
 * the route table.
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const isAdmin = useIsAdmin()
const zones = computed(() => accessibleSettingsZones(isAdmin.value))

/** The accessible zones split into labelled groups, omitting empty groups. */
const groups = computed<{ key: string; labelKey: string; zones: SettingsZone[] }[]>(() => {
  const account = zones.value.filter((zone) => !zone.adminOnly)
  const admin = zones.value.filter((zone) => zone.adminOnly)
  const result: { key: string; labelKey: string; zones: SettingsZone[] }[] = []
  if (admin.length > 0) {
    result.push({ key: 'admin', labelKey: 'settings.nav.administration', zones: admin })
  }
  if (account.length > 0) {
    result.push({ key: 'account', labelKey: 'settings.nav.account', zones: account })
  }
  return result
})

/** Headings only earn their place once there is more than one group to separate. */
const showGroupHeadings = computed(() => groups.value.length > 1)

/** Active styling applied to the zone that owns the current route. */
const ACTIVE_CLASS =
  'bg-brand-light font-medium text-brand-mid hover:bg-brand-light hover:text-brand-mid dark:bg-brand-dark-surface dark:text-brand-dark-foreground dark:hover:bg-brand-dark-surface dark:hover:text-brand-dark-foreground'

/**
 * Whether a zone owns the current route. Matches the zone's base path and any
 * nested route beneath it (e.g. the user detail page `/settings/users/:id`),
 * which a sibling route's default `active-class` wouldn't catch.
 *
 * @param zoneName - The zone's route name.
 * @returns Whether the zone is the active one.
 */
function isZoneActive(zoneName: string): boolean {
  const base = router.resolve({ name: zoneName }).path
  return route.path === base || route.path.startsWith(`${base}/`)
}

/** The zone owning the current route, shown in the mobile menu trigger. */
const activeZone = computed(() => zones.value.find((zone) => isZoneActive(zone.name)) ?? null)
</script>

<template>
  <div v-if="zones.length > 0">
    <!-- Below lg: a menu button (opens the zone list) instead of a tall stacked list. -->
    <div class="lg:hidden">
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline" class="w-full justify-between">
            <span class="flex min-w-0 items-center gap-2">
              <component
                :is="activeZone?.icon ?? Menu"
                class="size-4 shrink-0"
                aria-hidden="true"
              />
              <span class="truncate">
                {{ activeZone ? t(activeZone.labelKey) : t('settings.nav.label') }}
              </span>
            </span>
            <ChevronDown class="size-4 shrink-0 opacity-60" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" class="w-56">
          <template v-for="(group, index) in groups" :key="group.key">
            <DropdownMenuSeparator v-if="index > 0" />
            <DropdownMenuLabel v-if="showGroupHeadings">{{ t(group.labelKey) }}</DropdownMenuLabel>
            <DropdownMenuItem v-for="zone in group.zones" :key="zone.name" as-child>
              <RouterLink
                :to="{ name: zone.name }"
                :aria-current="isZoneActive(zone.name) ? 'page' : undefined"
              >
                <component :is="zone.icon" class="size-4 shrink-0" aria-hidden="true" />
                <span class="truncate">{{ t(zone.labelKey) }}</span>
                <Check
                  v-if="isZoneActive(zone.name)"
                  class="ml-auto size-4 shrink-0"
                  aria-hidden="true"
                />
              </RouterLink>
            </DropdownMenuItem>
          </template>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>

    <!-- lg and up: the full sidebar rail. -->
    <Card padding="none" class="hidden lg:block">
      <nav class="flex flex-col gap-1 p-3" :aria-label="t('settings.nav.label')">
        <template v-for="(group, index) in groups" :key="group.key">
          <hr v-if="index > 0" class="my-2 border-border" :aria-hidden="true" />
          <p v-if="showGroupHeadings" class="px-3 pb-1 pt-1 text-caption">
            {{ t(group.labelKey) }}
          </p>
          <RouterLink
            v-for="zone in group.zones"
            :key="zone.name"
            :to="{ name: zone.name }"
            class="flex items-center gap-3 rounded-input px-3 py-2 text-body transition-colors hover:bg-accent hover:text-accent-foreground"
            :class="isZoneActive(zone.name) ? ACTIVE_CLASS : ''"
            :aria-current="isZoneActive(zone.name) ? 'page' : undefined"
          >
            <component :is="zone.icon" class="size-4 shrink-0" aria-hidden="true" />
            {{ t(zone.labelKey) }}
          </RouterLink>
        </template>
      </nav>
    </Card>
  </div>
</template>
