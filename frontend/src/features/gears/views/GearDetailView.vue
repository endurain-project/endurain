<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft } from '@lucide/vue'

import type { Gear } from '@/features/gears/types'

import GearActivitiesPanel from '@/features/gears/components/GearActivitiesPanel.vue'
import GearComponentsPanel from '@/features/gears/components/GearComponentsPanel.vue'
import GearFormDialog from '@/features/gears/components/GearFormDialog.vue'
import GearInfoCard from '@/features/gears/components/GearInfoCard.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useToasts } from '@/composables/useToasts'
import { isStaleWrite } from '@/services/ifMatch'
import { presentGearType } from '@/features/gears/utils/gearType'
import { useDeleteGearMutation, useGearQuery } from '@/features/gears/composables/useGears'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const toasts = useToasts()
const { data: currentUser } = useCurrentUser()

const units = computed(() => currentUser.value?.units ?? 'metric')
const currency = computed(() => currentUser.value?.currency ?? 'euro')

const gearId = computed(() => {
  const raw = Number(route.params.id)
  return Number.isFinite(raw) && raw > 0 ? raw : null
})

const { data: gear, isPending, isError, refetch } = useGearQuery(gearId)

const typeLabel = computed(() =>
  gear.value ? t(presentGearType(gear.value.gearType).labelKey) : '',
)

// Edit dialog reuses the shared form; the detail is a superset of `Gear`.
const isFormOpen = ref(false)
const editingGear = computed<Gear | null>(() => gear.value ?? null)

function openEdit(): void {
  isFormOpen.value = true
}

function onFormSuccess(message: string): void {
  toasts.success(message)
}

function onFormError(message: string): void {
  toasts.error(message)
}

// Delete dialog; on success navigate back to the list.
const isDeleteOpen = ref(false)
const deleteMutation = useDeleteGearMutation()

function openDelete(): void {
  isDeleteOpen.value = true
}

function confirmDelete(): void {
  const target = gear.value
  if (!target) {
    return
  }
  deleteMutation.mutate(
    { id: target.id, version: target.version },
    {
      onSuccess: () => {
        isDeleteOpen.value = false
        toasts.success(t('gears.delete.success'))
        void router.push({ name: 'gears' })
      },
      onError: (error) =>
        toasts.error(isStaleWrite(error) ? t('app.staleError') : t('gears.delete.error')),
    },
  )
}
</script>

<template>
  <section class="flex flex-col gap-3">
    <Button
      variant="ghost"
      size="sm"
      class="self-start lg:hidden"
      @click="router.push({ name: 'gears' })"
    >
      <ArrowLeft class="size-4" aria-hidden="true" />
      {{ t('gears.detail.back') }}
    </Button>

    <!-- Loading: mirror the page header + the three-column layout (gear info,
         components list, activities list) so the placeholder matches the load. -->
    <template v-if="isPending">
      <header class="flex flex-col gap-1" aria-busy="true">
        <Skeleton class="h-7 w-48" />
        <Skeleton class="h-4 w-24" />
      </header>
      <div class="grid gap-3 lg:grid-cols-12 lg:items-start" aria-busy="true">
        <!-- Gear info -->
        <Card padding="none" class="divide-y divide-border overflow-hidden lg:col-span-4">
          <div class="px-4 py-3">
            <Skeleton class="h-5 w-28" />
          </div>
          <div class="flex flex-col gap-3 px-4 py-3">
            <Skeleton class="h-6 w-32 rounded-full" />
            <div class="flex flex-wrap gap-3">
              <Skeleton class="h-16 w-24 rounded-input" />
              <Skeleton class="h-16 w-24 rounded-input" />
              <Skeleton class="h-16 w-24 rounded-input" />
            </div>
            <div class="flex flex-col gap-3">
              <div v-for="n in 3" :key="n" class="space-y-1">
                <Skeleton class="h-3 w-16" />
                <Skeleton class="h-4 w-28" />
              </div>
            </div>
          </div>
          <div class="flex gap-2 px-4 py-3">
            <Skeleton class="h-9 w-20" />
            <Skeleton class="h-9 w-24" />
          </div>
        </Card>

        <!-- Components list -->
        <Card padding="none" class="divide-y divide-border overflow-hidden lg:col-span-4">
          <div class="px-4 py-3">
            <Skeleton class="h-5 w-32" />
          </div>
          <div class="divide-y divide-border">
            <div v-for="n in 3" :key="n" class="space-y-2 px-4 py-3">
              <Skeleton class="h-4 w-1/3" />
              <Skeleton class="h-3 w-1/5" />
              <Skeleton class="h-1.5 w-full" />
            </div>
          </div>
        </Card>

        <!-- Activities list -->
        <Card padding="none" class="divide-y divide-border overflow-hidden lg:col-span-4">
          <div class="px-4 py-3">
            <Skeleton class="h-5 w-28" />
          </div>
          <div class="divide-y divide-border">
            <div v-for="n in 5" :key="n" class="flex items-center justify-between gap-3 px-4 py-3">
              <Skeleton class="h-4 w-1/3" />
              <Skeleton class="h-3 w-20" />
            </div>
          </div>
        </Card>
      </div>
    </template>

    <!-- Error -->
    <ErrorState
      v-else-if="isError"
      :title="t('gears.error.title')"
      :description="t('gears.error.description')"
      @retry="() => refetch()"
    >
      <template #action="{ retry }">
        <Button variant="outline" @click="retry">{{ t('gears.error.retry') }}</Button>
      </template>
    </ErrorState>

    <!-- Not found -->
    <EmptyState
      v-else-if="!gear"
      :title="t('gears.detail.notFoundTitle')"
      :description="t('gears.detail.notFoundDescription')"
    >
      <template #action>
        <Button variant="outline" @click="router.push({ name: 'gears' })">
          {{ t('gears.detail.back') }}
        </Button>
      </template>
    </EmptyState>

    <!-- Content -->
    <template v-else>
      <header class="flex flex-col gap-1">
        <h1 class="text-page-title">{{ gear.nickname }}</h1>
        <p class="text-body">{{ typeLabel }}</p>
      </header>
      <!-- v1-style layout: a single stacked column on mobile, a three-column row
           (gear info | components | activities) from lg up. -->
      <div class="grid gap-3 lg:grid-cols-12 lg:items-start">
        <GearInfoCard
          class="lg:col-span-4"
          :gear="gear"
          :units="units"
          :currency="currency"
          @edit="openEdit"
          @delete="openDelete"
        />
        <GearComponentsPanel
          class="lg:col-span-4"
          :gear="gear"
          :units="units"
          :currency="currency"
        />
        <GearActivitiesPanel class="lg:col-span-4" :gear-id="gear.id" />
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
        :description="t('gears.delete.body', { nickname: gear.nickname })"
        :confirm-label="t('gears.delete.confirm')"
        :cancel-label="t('gears.delete.cancel')"
        :close-label="t('gears.delete.close')"
        :pending="deleteMutation.isPending.value"
        @confirm="confirmDelete"
      />
    </template>
  </section>
</template>
