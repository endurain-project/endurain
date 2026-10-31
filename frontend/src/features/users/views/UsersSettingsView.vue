<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Filter, Plus, Search, UserX, X } from '@lucide/vue'

import type { ManagedUser, UserFilters } from '@/features/users/types'

import UserFormDialog from '@/features/users/components/UserFormDialog.vue'
import UserListItem from '@/features/users/components/UserListItem.vue'
import UserPasswordDialog from '@/features/users/components/UserPasswordDialog.vue'
import { Button } from '@/components/ui/button'
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
  useApproveUserMutation,
  useDeleteUserMutation,
  useUsersQuery,
} from '@/features/users/composables/useUsers'

const { t } = useI18n()
const toasts = useToasts()
const { data: currentUser } = useCurrentUser()

/** Filter defaults: hide inactive accounts, show everything else (matches v1). */
const DEFAULT_FILTERS: UserFilters = {
  showInactive: false,
  showEmailUnverified: true,
  showPendingApproval: true,
  showExternalAuth: true,
  showLocalAuth: true,
}

/** The five list filters, surfaced in the Filters popover. */
const filters = reactive<UserFilters>({ ...DEFAULT_FILTERS })

/** Filter rows grouped for the popover; a divider separates each group (mirrors v1). */
const FILTER_GROUPS: { key: keyof UserFilters; labelKey: string }[][] = [
  [{ key: 'showInactive', labelKey: 'settings.users.showInactive' }],
  [
    { key: 'showEmailUnverified', labelKey: 'settings.users.showEmailUnverified' },
    { key: 'showPendingApproval', labelKey: 'settings.users.showPendingApproval' },
  ],
  [
    { key: 'showExternalAuth', labelKey: 'settings.users.showExternalAuth' },
    { key: 'showLocalAuth', labelKey: 'settings.users.showLocalAuth' },
  ],
]

const isFilterOpen = ref(false)
const page = ref(1)
const searchTerm = ref('')
const debouncedSearch = ref('')

// Page size follows the server's enforced `num_records_per_page` setting.
const { recordsPerPage } = useRecordsPerPage()

// Debounce the username search so typing doesn't fire a request per keystroke.
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

/** Clears the username search field and immediately exits search mode. */
function clearSearch(): void {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTerm.value = ''
  debouncedSearch.value = ''
}

const isSearching = computed(() => debouncedSearch.value.trim().length > 0)

// The username search is a server-side filter on the same paginated list.
const listQuery = useUsersQuery(page, recordsPerPage, () => ({
  ...filters,
  username: debouncedSearch.value.trim(),
}))

/** Users on the current page. */
const listUsers = computed(() => listQuery.data.value?.records ?? [])
/** Server-reported total across all pages (list mode). */
const totalCount = computed(() => listQuery.data.value?.total ?? 0)

// Numbered pagination: derives the page count and clamps the page when the
// total shrinks (e.g. after deleting the last user on the final page).
const { totalPages, reset: resetPage } = useListPagination(page, totalCount, recordsPerPage)

const isPending = computed(() => listQuery.isPending.value)
const isError = computed(() => listQuery.isError.value)
const isEmpty = computed(() => !isPending.value && !isError.value && listUsers.value.length === 0)
/** Number of filters deviating from their default, shown as a badge. */
const activeFilterCount = computed(
  () =>
    (Object.keys(DEFAULT_FILTERS) as (keyof UserFilters)[]).filter(
      (key) => filters[key] !== DEFAULT_FILTERS[key],
    ).length,
)

/**
 * Empty-state copy. Distinguishes a genuinely empty instance (first-time CTA)
 * from a search or filter miss (a quiet "no matches" line) so active filters
 * never surface the misleading "No users yet" banner.
 */
const emptyState = computed<{
  title: string
  description?: string
  variant: 'first-time' | 'filtered'
}>(() => {
  if (isSearching.value) {
    return { title: t('settings.users.empty.searchTitle'), variant: 'filtered' }
  }
  if (activeFilterCount.value > 0) {
    return { title: t('settings.users.empty.filteredTitle'), variant: 'filtered' }
  }
  return {
    title: t('settings.users.empty.title'),
    description: t('settings.users.empty.description'),
    variant: 'first-time',
  }
})

// Changing a filter or the search term alters the result set, so restart at the first page.
watch([filters, debouncedSearch], resetPage)

/** Refetches the list after an error. */
function refetchActive(): void {
  void listQuery.refetch()
}

/** Whether a row is the signed-in admin's own account (no self-delete). */
function isSelf(user: ManagedUser): boolean {
  return currentUser.value?.id === user.id
}

// Add/edit dialog state. `editingUser` null means "add".
const isFormOpen = ref(false)
const editingUser = ref<ManagedUser | null>(null)

function openAdd(): void {
  editingUser.value = null
  isFormOpen.value = true
}

function openEdit(user: ManagedUser): void {
  editingUser.value = user
  isFormOpen.value = true
}

function onFormSuccess(message: string): void {
  toasts.success(message)
}

function onFormError(message: string): void {
  toasts.error(message)
}

// Reset-password dialog state. Opened from a row without leaving the list.
const isPasswordOpen = ref(false)
const passwordUser = ref<ManagedUser | null>(null)

function openPassword(user: ManagedUser): void {
  passwordUser.value = user
  isPasswordOpen.value = true
}

// Delete dialog state.
const isDeleteOpen = ref(false)
const userToDelete = ref<ManagedUser | null>(null)
const deleteMutation = useDeleteUserMutation()

function openDelete(user: ManagedUser): void {
  userToDelete.value = user
  isDeleteOpen.value = true
}

function confirmDelete(): void {
  const user = userToDelete.value
  if (!user) {
    return
  }
  deleteMutation.mutate(
    { id: user.id, version: user.version },
    {
      onSuccess: () => {
        isDeleteOpen.value = false
        toasts.success(t('settings.users.delete.success'))
      },
      onError: (error) =>
        toasts.error(isStaleWrite(error) ? t('app.staleError') : t('settings.users.delete.error')),
    },
  )
}

// Pending sign-up moderation: approve clears the pending flag; reject deletes the
// account after confirmation.
const approveMutation = useApproveUserMutation()
const isRejectOpen = ref(false)
const userToReject = ref<ManagedUser | null>(null)

function approve(user: ManagedUser): void {
  approveMutation.mutate(user.id, {
    onSuccess: () => toasts.success(t('settings.users.approval.approveSuccess')),
    onError: () => toasts.error(t('settings.users.approval.approveError')),
  })
}

function openReject(user: ManagedUser): void {
  userToReject.value = user
  isRejectOpen.value = true
}

function confirmReject(): void {
  const user = userToReject.value
  if (!user) {
    return
  }
  deleteMutation.mutate(
    { id: user.id, version: user.version },
    {
      onSuccess: () => {
        isRejectOpen.value = false
        toasts.success(t('settings.users.approval.rejectSuccess'))
      },
      onError: (error) =>
        toasts.error(
          isStaleWrite(error) ? t('app.staleError') : t('settings.users.approval.rejectError'),
        ),
    },
  )
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-col gap-1">
        <h1 class="text-page-title">{{ t('settings.users.title') }}</h1>
        <p class="text-body">{{ t('settings.users.subtitle') }}</p>
      </div>
      <Button class="w-full sm:w-auto" @click="openAdd">
        <Plus class="size-4" aria-hidden="true" />
        {{ t('settings.users.buttonAddUser') }}
      </Button>
    </div>

    <div class="relative">
      <Search
        class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        v-model="searchTerm"
        type="search"
        :placeholder="t('settings.users.searchPlaceholder')"
        :aria-label="t('settings.users.searchPlaceholder')"
        class="w-full pl-9 pr-9"
      />
      <button
        v-if="searchTerm"
        type="button"
        class="absolute right-1 top-1/2 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-input text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
        :aria-label="t('settings.users.clearSearch')"
        @click="clearSearch"
      >
        <X class="size-4" aria-hidden="true" />
      </button>
    </div>

    <ListPanel
      v-model:page="page"
      :is-loading="isPending"
      :is-error="isError"
      :is-empty="isEmpty"
      :show-header="!isError"
      :error-title="t('settings.users.error.title')"
      :error-description="t('settings.users.error.description')"
      :retry-label="t('settings.users.error.retry')"
      paginated
      :total-pages="totalPages"
      @retry="refetchActive"
    >
      <template #header>
        <div class="flex items-center justify-end px-4 py-3">
          <Popover v-model:open="isFilterOpen">
            <PopoverTrigger as-child>
              <Button variant="outline" size="sm">
                <Filter class="size-4" aria-hidden="true" />
                {{ t('settings.users.filters') }}
                <CountBadge :count="activeFilterCount" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" class="w-64">
              <div class="flex flex-col">
                <template v-for="(group, groupIndex) in FILTER_GROUPS" :key="groupIndex">
                  <div v-if="groupIndex > 0" role="separator" class="-mx-1 my-1 h-px bg-border" />
                  <Switch
                    v-for="option in group"
                    :key="option.key"
                    v-model="filters[option.key]"
                    class="w-full"
                  >
                    {{ t(option.labelKey) }}
                  </Switch>
                </template>
              </div>
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
              <Skeleton class="h-3 w-2/5" />
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
            <UserX class="size-8" aria-hidden="true" />
          </template>
        </EmptyState>
      </template>

      <ul class="divide-y divide-border">
        <li v-for="user in listUsers" :key="user.id">
          <UserListItem
            :user="user"
            :is-self="isSelf(user)"
            @password="openPassword"
            @edit="openEdit"
            @delete="openDelete"
            @approve="approve"
            @reject="openReject"
          />
        </li>
      </ul>
    </ListPanel>

    <UserFormDialog
      v-model:open="isFormOpen"
      :user="editingUser"
      :is-self="editingUser !== null && isSelf(editingUser)"
      @success="onFormSuccess"
      @error="onFormError"
    />
    <ConfirmDialog
      v-model:open="isDeleteOpen"
      :title="t('settings.users.delete.title')"
      :description="t('settings.users.delete.body', { name: userToDelete?.name ?? '' })"
      :confirm-label="t('settings.users.delete.confirm')"
      :cancel-label="t('settings.users.delete.cancel')"
      :close-label="t('settings.users.delete.close')"
      :pending="deleteMutation.isPending.value"
      @confirm="confirmDelete"
    />
    <ConfirmDialog
      v-model:open="isRejectOpen"
      :title="t('settings.users.approval.rejectTitle')"
      :description="
        t('settings.users.approval.rejectBody', { username: userToReject?.username ?? '' })
      "
      :confirm-label="t('settings.users.approval.rejectConfirm')"
      :cancel-label="t('settings.users.approval.rejectCancel')"
      :close-label="t('settings.users.approval.rejectClose')"
      :pending="deleteMutation.isPending.value"
      @confirm="confirmReject"
    />
    <UserPasswordDialog
      v-model:open="isPasswordOpen"
      :user-id="passwordUser?.id ?? 0"
      :username="passwordUser?.username ?? ''"
      :access-type="passwordUser?.accessType ?? 'regular'"
      @success="onFormSuccess"
      @error="onFormError"
    />
  </div>
</template>
