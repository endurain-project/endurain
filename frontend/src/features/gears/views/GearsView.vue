<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Filter, Plus, Search, Wrench, X } from '@lucide/vue'

import type { Gear } from '@/features/gears/types'

import GearFormDialog from '@/features/gears/components/GearFormDialog.vue'
import GearListItem from '@/features/gears/components/GearListItem.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { CountBadge } from '@/components/ui/count-badge'
import { EmptyState } from '@/components/ui/empty-state'
import { Input } from '@/components/ui/input'
import { ListPanel } from '@/components/ui/list-panel'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useRecordsPerPage } from '@/features/config/composables/useRecordsPerPage'
import { useListPagination } from '@/composables/useListPagination'
import { useToasts } from '@/composables/useToasts'
import { isStaleWrite } from '@/services/ifMatch'
import {
  useDeleteGearMutation,
  useGearSearchQuery,
  useGearsQuery,
} from '@/features/gears/composables/useGears'

const { t } = useI18n()
const toasts = useToasts()
const { data: currentUser } = useCurrentUser()

const units = computed(() => currentUser.value?.units ?? 'metric')
const currency = computed(() => currentUser.value?.currency ?? 'euro')

const showInactive = ref(false)
const isFilterOpen = ref(false)
const page = ref(1)
const searchTerm = ref('')
const debouncedSearch = ref('')

// Page size follows the server's enforced `num_records_per_page` setting.
const { recordsPerPage } = useRecordsPerPage()

// Debounce the nickname search so typing doesn't fire a request per keystroke.
let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(searchTerm, (value) => {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTimer = setTimeout(() => {
    debouncedSearch.value = value
  }, 400)
})
onBeforeUnmount(() => {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
})

/** Clears the nickname search field and immediately exits search mode. */
function clearSearch(): void {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTerm.value = ''
  debouncedSearch.value = ''
}

const isSearching = computed(() => debouncedSearch.value.trim().length > 0)

const listQuery = useGearsQuery(page, recordsPerPage, showInactive)
const searchQuery = useGearSearchQuery(debouncedSearch)

/** Gears on the current page. */
const listGears = computed(() => listQuery.data.value?.records ?? [])
/** Server-reported total across all pages (list mode). */
const totalCount = computed(() => listQuery.data.value?.total ?? 0)

// Numbered pagination: derives the page count and clamps the page when the
// total shrinks (e.g. after deleting the last gear on the final page).
const { totalPages, reset: resetPage } = useListPagination(page, totalCount, recordsPerPage)

// The view has two modes that share one render path: live nickname search vs.
// the paginated list. `isSearching` selects which query drives the UI.
const displayedGears = computed(() =>
  isSearching.value ? (searchQuery.data.value ?? []) : listGears.value,
)
const isPending = computed(() =>
  isSearching.value ? searchQuery.isPending.value : listQuery.isPending.value,
)
const isError = computed(() =>
  isSearching.value ? searchQuery.isError.value : listQuery.isError.value,
)
const isEmpty = computed(
  () => !isPending.value && !isError.value && displayedGears.value.length === 0,
)
/** Number of active filters, surfaced as a badge on the Filters trigger. */
const activeFilterCount = computed(() => (showInactive.value ? 1 : 0))

/**
 * Empty-state copy. With inactive gear hidden (the default), an empty list can
 * still mean the user has inactive gear, so the message points at the
 * "Show inactive" filter instead of implying there is no gear at all.
 */
const emptyState = computed<{
  title: string
  description?: string
  variant: 'first-time' | 'filtered'
}>(() => {
  if (isSearching.value) {
    return {
      title: t('gears.empty.searchTitle'),
      description: t('gears.empty.searchDescription'),
      variant: 'filtered',
    }
  }
  if (!showInactive.value) {
    return {
      title: t('gears.empty.activeTitle'),
      description: t('gears.empty.activeDescription'),
      variant: 'first-time',
    }
  }
  return {
    title: t('gears.empty.title'),
    description: t('gears.empty.description'),
    variant: 'first-time',
  }
})

// Toggling a filter changes the result set, so restart at the first page.
watch(showInactive, resetPage)

/** Refetches whichever query currently drives the view. */
function refetchActive(): void {
  if (isSearching.value) {
    void searchQuery.refetch()
  } else {
    void listQuery.refetch()
  }
}

// Add/edit dialog state. `editingGear` null means "add".
const isFormOpen = ref(false)
const editingGear = ref<Gear | null>(null)

function openAdd(): void {
  editingGear.value = null
  isFormOpen.value = true
}

function openEdit(gear: Gear): void {
  editingGear.value = gear
  isFormOpen.value = true
}

function onFormSuccess(message: string): void {
  toasts.success(message)
}

function onFormError(message: string): void {
  toasts.error(message)
}

// Delete dialog state.
const isDeleteOpen = ref(false)
const gearToDelete = ref<Gear | null>(null)
const deleteMutation = useDeleteGearMutation()

function openDelete(gear: Gear): void {
  gearToDelete.value = gear
  isDeleteOpen.value = true
}

function confirmDelete(): void {
  const gear = gearToDelete.value
  if (!gear) {
    return
  }
  deleteMutation.mutate(
    { id: gear.id, version: gear.version },
    {
      onSuccess: () => {
        isDeleteOpen.value = false
        toasts.success(t('gears.delete.success'))
      },
      onError: (error) =>
        toasts.error(isStaleWrite(error) ? t('app.staleError') : t('gears.delete.error')),
    },
  )
}
</script>

<template>
  <section class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('gears.title') }}</h1>
      <p class="text-body">{{ t('gears.subtitle') }}</p>
    </header>

    <!--
      Two-column shell on lg+: a controls rail beside the list. Below lg the rail
      collapses to the top of the normal flow, so the same content appears at every
      breakpoint (no desktop-only sidebar that disappears on mobile).
    -->
    <div class="grid gap-3 lg:grid-cols-[18rem_minmax(0,1fr)] lg:items-start">
      <!-- Controls rail: add + nickname search. -->
      <aside class="lg:sticky lg:top-6">
        <Card class="flex flex-col gap-3">
          <Button class="w-full" @click="openAdd">
            <Plus class="size-4" aria-hidden="true" />
            {{ t('gears.buttonAddGear') }}
          </Button>

          <div class="relative">
            <Search
              class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              v-model="searchTerm"
              type="search"
              :placeholder="t('gears.searchPlaceholder')"
              :aria-label="t('gears.searchPlaceholder')"
              class="w-full pl-9 pr-9"
            />
            <button
              v-if="searchTerm"
              type="button"
              class="absolute right-1 top-1/2 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-input text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
              :aria-label="t('gears.clearSearch')"
              @click="clearSearch"
            >
              <X class="size-4" aria-hidden="true" />
            </button>
          </div>
        </Card>
      </aside>

      <!--
        Main panel: the filters header, the list/states, and the pager share one
        surface so their backgrounds align (mirrors v1's list panel).
      -->
      <ListPanel
        v-model:page="page"
        :is-loading="isPending"
        :is-error="isError"
        :is-empty="isEmpty"
        :show-header="!isError && !isSearching"
        :error-title="t('gears.error.title')"
        :error-description="t('gears.error.description')"
        :retry-label="t('gears.error.retry')"
        :paginated="!isSearching"
        :total-pages="totalPages"
        @retry="refetchActive"
      >
        <template #header>
          <div class="flex items-center justify-end px-4 py-3">
            <Popover v-model:open="isFilterOpen">
              <PopoverTrigger as-child>
                <Button variant="outline" size="sm">
                  <Filter class="size-4" aria-hidden="true" />
                  {{ t('gears.filters') }}
                  <CountBadge :count="activeFilterCount" />
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" class="w-56">
                <Switch v-model="showInactive" class="w-full">
                  {{ t('gears.showInactive') }}
                </Switch>
              </PopoverContent>
            </Popover>
          </div>
        </template>

        <template #loading>
          <div class="divide-y divide-border" aria-busy="true">
            <div v-for="n in 6" :key="n" class="flex items-center gap-3 px-4 py-3">
              <Skeleton class="size-10 shrink-0 rounded-full" />
              <div class="flex-1 space-y-2">
                <Skeleton class="h-4 w-1/3" />
                <Skeleton class="h-3 w-1/5" />
              </div>
            </div>
          </div>
        </template>

        <template #empty>
          <EmptyState
            :title="emptyState.title"
            :description="emptyState.description"
            :variant="emptyState.variant"
          >
            <template #icon>
              <Wrench class="size-8" aria-hidden="true" />
            </template>
            <template v-if="emptyState.variant === 'first-time'" #action>
              <Button @click="openAdd">
                <Plus class="size-4" aria-hidden="true" />
                {{ t('gears.buttonAddGear') }}
              </Button>
            </template>
          </EmptyState>
        </template>

        <ul class="divide-y divide-border">
          <li v-for="gear in displayedGears" :key="gear.id">
            <GearListItem :gear="gear" @edit="openEdit" @delete="openDelete" />
          </li>
        </ul>
      </ListPanel>
    </div>

    <GearFormDialog
      v-model:open="isFormOpen"
      :gear="editingGear"
      :units="units"
      :currency="currency"
      @success="onFormSuccess"
      @error="onFormError"
    />
    <ConfirmDialog
      v-model:open="isDeleteOpen"
      :title="t('gears.delete.title')"
      :description="t('gears.delete.body', { nickname: gearToDelete?.nickname ?? '' })"
      :confirm-label="t('gears.delete.confirm')"
      :cancel-label="t('gears.delete.cancel')"
      :close-label="t('gears.delete.close')"
      :pending="deleteMutation.isPending.value"
      @confirm="confirmDelete"
    />
  </section>
</template>
