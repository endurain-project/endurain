<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Activity as ActivityIcon, Search, Users as UsersIcon, Wrench, X } from '@lucide/vue'
import type { LucideIcon } from '@lucide/vue'

import type { SearchScope } from '@/features/search/types'

import ActivityResultItem from '@/features/search/components/ActivityResultItem.vue'
import GearResultItem from '@/features/search/components/GearResultItem.vue'
import UserResultItem from '@/features/search/components/UserResultItem.vue'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { Input } from '@/components/ui/input'
import { ListPanel } from '@/components/ui/list-panel'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSearch } from '@/features/search/composables/useSearch'
import {
  ACTIVITY_CATEGORY_FILTERS,
  ALL_ACTIVITY_CATEGORIES,
  ALL_GEAR_TYPES,
} from '@/features/search/utils/filters'
import { GEAR_TYPE_VALUES, presentGearType } from '@/features/gears/utils/gearType'

const { t } = useI18n()

const {
  scope,
  searchTerm,
  debouncedSearch,
  activityCategory,
  gearTypeFilter,
  isSearching,
  minUserSearchLength,
  isPending,
  isError,
  isEmpty,
  userResults,
  activityResults,
  gearResults,
  clearSearch,
  refetchActive,
} = useSearch()

/** The scope tab options, in display order. */
const SCOPE_OPTIONS: ReadonlyArray<{ value: SearchScope; labelKey: string; icon: LucideIcon }> = [
  { value: 'users', labelKey: 'search.scopes.users', icon: UsersIcon },
  { value: 'activities', labelKey: 'search.scopes.activities', icon: ActivityIcon },
  { value: 'gears', labelKey: 'search.scopes.gears', icon: Wrench },
]

/**
 * String proxy for the Tabs primitive (its model is a plain `string`), keeping
 * the `scope` ref strongly typed as `SearchScope` for the rest of the view;
 * unknown values are ignored.
 */
const scopeModel = computed<string>({
  get: () => scope.value,
  set: (value) => {
    const match = SCOPE_OPTIONS.find((option) => option.value === value)
    if (match) {
      scope.value = match.value
    }
  },
})
</script>

<template>
  <section class="mx-auto flex w-full max-w-2xl flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('search.title') }}</h1>
      <p class="text-body">{{ t('search.subtitle') }}</p>
    </header>

    <!-- Controls: scope tab options + the debounced search box. -->
    <Card class="flex flex-col gap-3">
      <Tabs v-model="scopeModel">
        <TabsList class="grid w-full grid-cols-3" :aria-label="t('search.title')">
          <TabsTrigger
            v-for="option in SCOPE_OPTIONS"
            :key="option.value"
            :value="option.value"
            class="gap-1.5"
          >
            <component :is="option.icon" class="size-4" aria-hidden="true" />
            {{ t(option.labelKey) }}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <!-- Sub-type filter for the active scope (activities and gear only). -->
      <Select
        v-if="scope === 'activities'"
        v-model="activityCategory"
        :aria-label="t('search.filters.activityType')"
      >
        <option :value="ALL_ACTIVITY_CATEGORIES">{{ t('search.filters.all') }}</option>
        <option
          v-for="category in ACTIVITY_CATEGORY_FILTERS"
          :key="category.value"
          :value="category.value"
        >
          {{ t(`search.activityCategories.${category.value}`) }}
        </option>
      </Select>
      <Select
        v-else-if="scope === 'gears'"
        v-model="gearTypeFilter"
        :aria-label="t('search.filters.gearType')"
      >
        <option :value="ALL_GEAR_TYPES">{{ t('search.filters.all') }}</option>
        <option v-for="type in GEAR_TYPE_VALUES" :key="type" :value="type">
          {{ t(presentGearType(type).labelKey) }}
        </option>
      </Select>

      <div class="relative">
        <Search
          class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          v-model="searchTerm"
          type="search"
          :placeholder="t('search.placeholder')"
          :aria-label="t('search.placeholder')"
          class="w-full pl-9 pr-9"
        />
        <button
          v-if="searchTerm"
          type="button"
          class="absolute right-1 top-1/2 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-input text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
          :aria-label="t('search.clear')"
          @click="clearSearch"
        >
          <X class="size-4" aria-hidden="true" />
        </button>
      </div>
    </Card>

    <!--
      Results panel. Loading/error only apply while a search is active; when the
      box is empty the panel shows the idle prompt via its empty slot.
    -->
    <ListPanel
      :is-loading="isSearching && isPending"
      :is-error="isSearching && isError"
      :is-empty="!isSearching || isEmpty"
      :show-header="false"
      :error-title="t('search.error.title')"
      :error-description="t('search.error.description')"
      :retry-label="t('search.error.retry')"
      :paginated="false"
      @retry="refetchActive"
    >
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
          :title="isSearching ? t('search.empty.title') : t('search.idle.title')"
          :description="
            isSearching
              ? t('search.empty.description', { term: debouncedSearch })
              : scope === 'users'
                ? t('search.idle.usersDescription', { min: minUserSearchLength })
                : t('search.idle.description')
          "
          :variant="isSearching ? 'filtered' : 'first-time'"
        >
          <template #icon>
            <Search class="size-8" aria-hidden="true" />
          </template>
        </EmptyState>
      </template>

      <ul class="divide-y divide-border">
        <template v-if="scope === 'users'">
          <li v-for="user in userResults" :key="user.id">
            <UserResultItem :user="user" />
          </li>
        </template>
        <template v-else-if="scope === 'activities'">
          <li v-for="activity in activityResults" :key="activity.id">
            <ActivityResultItem :activity="activity" />
          </li>
        </template>
        <template v-else>
          <li v-for="gear in gearResults" :key="gear.id">
            <GearResultItem :gear="gear" />
          </li>
        </template>
      </ul>
    </ListPanel>
  </section>
</template>
