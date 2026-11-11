<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave, useRoute, useRouter, type RouteLocationNormalized } from 'vue-router'

import type { ServerSettings, TileMapsTemplate } from '@/features/serverSettings/types'

import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import SectionTabsBar from '@/components/SectionTabsBar.vue'
import { Tabs, TabsContent } from '@/components/ui/tabs'
import StepUpDialog from '@/features/security/components/StepUpDialog.vue'
import { useAdminStepUp } from '@/features/security/composables/useAdminStepUp'
import { useMailStepUpResume } from '@/features/serverSettings/composables/useMailStepUpResume'
import EmailCard from '@/features/serverSettings/components/EmailCard.vue'
import ServerSettingsSearch from '@/features/serverSettings/components/ServerSettingsSearch.vue'
import AccessTab from '@/features/serverSettings/components/tabs/AccessTab.vue'
import GeneralTab from '@/features/serverSettings/components/tabs/GeneralTab.vue'
import LogsTab from '@/features/serverSettings/components/tabs/LogsTab.vue'
import MapsTab from '@/features/serverSettings/components/tabs/MapsTab.vue'
import UnsavedChangesBar from '@/features/serverSettings/components/UnsavedChangesBar.vue'
import {
  provideServerSettingsForm,
  useServerSettingsForm,
} from '@/features/serverSettings/composables/useServerSettingsForm'
import type { SettingsSearchResult } from '@/features/serverSettings/searchIndex'
import {
  DEFAULT_SETTINGS_TAB,
  parseSettingsTab,
  SETTINGS_TABS,
  type SettingsTab,
} from '@/features/serverSettings/settingsTabs'

const props = defineProps<{
  /** The loaded server settings; seeds the form (the parent mounts this only after load). */
  settings: ServerSettings
  /** Available tile-server presets for the maps tab. */
  templates: TileMapsTemplate[]
}>()

/**
 * The server settings page body: a search box, the tabs, and one form shared
 * across the General, Access and Maps tabs so a single save and a single
 * unsaved-changes state cover them. The Email tab keeps its own form and save.
 * The active tab lives in the `?tab=` query so it can be linked and survives the
 * rebuild that follows a save.
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const form = useServerSettingsForm(props)
provideServerSettingsForm(form)
const {
  isDirty,
  isValid,
  isSubmitting,
  dirtyTabs,
  handleSubmit,
  discard,
  isStepUpOpen,
  idpReauth,
  draftValues,
  confirmStepUp,
  isUpdating,
} = form
const { requirePassword, requireMfa } = useAdminStepUp()

const root = ref<HTMLElement | null>(null)
// The sign-in the page returned from for the mail settings lands the user on the tab that holds them.
const returnedForMail = useMailStepUpResume().value !== null
const mailDirty = ref(false)
const hasUnsaved = computed(() => isDirty.value || mailDirty.value)

// The logs tab exists only where the backend offers the viewer.
const visibleTabs = computed(() =>
  SETTINGS_TABS.filter((tab) => tab !== 'logs' || props.settings.logsViewerEnabled),
)

const activeTab = computed(() => {
  const tab = parseSettingsTab(route.query.tab)
  return visibleTabs.value.includes(tab) ? tab : DEFAULT_SETTINGS_TAB
})

/**
 * Whether a tab holds unsaved edits.
 *
 * @param tab - The tab to check.
 * @returns True when the tab has edits.
 */
function isTabDirty(tab: SettingsTab): boolean {
  return tab === 'email' ? mailDirty.value : dirtyTabs.value.has(tab)
}

const barTabs = computed(() =>
  visibleTabs.value.map((tab) => ({
    value: tab,
    label: t(`settings.server.tabs.${tab}`),
    dirty: isTabDirty(tab),
  })),
)

/**
 * Switches tab by updating the URL, keeping any other query params.
 *
 * @param value - The tab the user picked.
 * @returns Resolves once the navigation settles.
 */
async function selectTab(value: string | number): Promise<void> {
  await router.replace({ query: { ...route.query, tab: parseSettingsTab(value) } })
}

/** Classes that flash a ring around the element a search result points at. */
const HIGHLIGHT_CLASSES = ['ring-2', 'ring-ring', 'ring-offset-2', 'ring-offset-background']
const HIGHLIGHT_MS = 1500

/**
 * Jumps to a search result: opens its tab, scrolls the setting into view,
 * focuses its control and briefly highlights it. A setting that is not on the
 * page right now (for example a field of another geocoding service) falls back
 * to its section.
 *
 * @param result - The chosen search result.
 */
async function jumpTo(result: SettingsSearchResult): Promise<void> {
  await selectTab(result.entry.tab)
  await nextTick()
  const { id, sectionId } = result.entry
  const target =
    root.value?.querySelector<HTMLElement>(`[data-setting="${id}"]`) ??
    (sectionId ? root.value?.querySelector<HTMLElement>(`[data-setting="${sectionId}"]`) : null)
  if (!target) {
    return
  }
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' })
  if (id !== sectionId) {
    target.querySelector<HTMLElement>('input, select, textarea')?.focus({ preventScroll: true })
  }
  target.classList.add(...HIGHLIGHT_CLASSES)
  setTimeout(() => target.classList.remove(...HIGHLIGHT_CLASSES), HIGHLIGHT_MS)
}

const leaveTarget = ref<RouteLocationNormalized | null>(null)
const leaveOpen = computed({
  get: () => leaveTarget.value !== null,
  set: (open: boolean) => {
    if (!open) {
      leaveTarget.value = null
    }
  },
})
let allowLeave = false

// Leaving the page with edits held back asks first; the user's choice resumes the navigation.
onBeforeRouteLeave((to) => {
  if (allowLeave || !hasUnsaved.value) {
    return true
  }
  leaveTarget.value = to
  return false
})

/** Resumes the navigation the guard held back. */
function confirmLeave(): void {
  const target = leaveTarget.value
  allowLeave = true
  leaveTarget.value = null
  if (target) {
    void router.push(target.fullPath)
  }
}

/**
 * Asks the browser to confirm closing or reloading the tab while edits are unsaved.
 *
 * @param event - The `beforeunload` event.
 */
function warnBeforeUnload(event: BeforeUnloadEvent): void {
  if (hasUnsaved.value) {
    event.preventDefault()
  }
}

onMounted(() => {
  window.addEventListener('beforeunload', warnBeforeUnload)
  if (returnedForMail) {
    void selectTab('email')
  }
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', warnBeforeUnload))
</script>

<template>
  <div ref="root" class="flex flex-col gap-3">
    <Tabs class="flex flex-col gap-3" :model-value="activeTab" @update:model-value="selectTab">
      <div class="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-center lg:justify-between">
        <SectionTabsBar
          :model-value="activeTab"
          :tabs="barTabs"
          :label="t('settings.server.tabs.label')"
          :unsaved-label="t('settings.server.tabs.unsaved')"
          @update:model-value="selectTab"
        />
        <ServerSettingsSearch @select="jumpTo" />
      </div>

      <!-- Every panel stays mounted so the Email form keeps its edits while another tab is open. -->
      <TabsContent value="general" force-mount class="mt-0 data-[state=inactive]:hidden">
        <GeneralTab />
      </TabsContent>
      <TabsContent value="access" force-mount class="mt-0 data-[state=inactive]:hidden">
        <AccessTab />
      </TabsContent>
      <TabsContent value="maps" force-mount class="mt-0 data-[state=inactive]:hidden">
        <MapsTab />
      </TabsContent>
      <TabsContent value="email" force-mount class="mt-0 data-[state=inactive]:hidden">
        <EmailCard @dirty-change="mailDirty = $event" />
      </TabsContent>
      <!-- Not force-mounted: the log tail polls only while its tab is open. -->
      <TabsContent v-if="visibleTabs.includes('logs')" value="logs" class="mt-0">
        <LogsTab />
      </TabsContent>
    </Tabs>

    <UnsavedChangesBar
      v-if="isDirty"
      :saving="isSubmitting"
      :can-save="isValid"
      @save="handleSubmit"
      @discard="discard"
    />

    <StepUpDialog
      v-model:open="isStepUpOpen"
      v-model:reauth="idpReauth"
      action="admin_server_settings_edit"
      :title="t('settings.server.stepUpTitle')"
      :description="t('settings.server.stepUpDescription')"
      :confirm-label="t('settings.server.save')"
      :require-password="requirePassword"
      :require-mfa="requireMfa"
      :pending-context="{ draft: draftValues() }"
      :pending="isUpdating"
      @confirm="confirmStepUp"
    />

    <ConfirmDialog
      v-model:open="leaveOpen"
      :title="t('settings.server.leave.title')"
      :description="t('settings.server.leave.description')"
      :confirm-label="t('settings.server.leave.confirm')"
      :cancel-label="t('settings.server.leave.stay')"
      :close-label="t('settings.server.leave.close')"
      @confirm="confirmLeave"
    />
  </div>
</template>
