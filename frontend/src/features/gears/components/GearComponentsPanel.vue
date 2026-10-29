<script setup lang="ts">
import { computed, ref } from 'vue'
import { Filter, Plus } from '@lucide/vue'

import type { Gear, GearComponent } from '@/features/gears/types'
import type { Schemas } from '@/types'

import GearComponentFormDialog from '@/features/gears/components/GearComponentFormDialog.vue'
import GearComponentListItem from '@/features/gears/components/GearComponentListItem.vue'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { CountBadge } from '@/components/ui/count-badge'
import { ListPanel } from '@/components/ui/list-panel'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { useToasts } from '@/composables/useToasts'
import {
  componentTypeListKey,
  gearTypeSupportsComponents,
} from '@/features/gears/utils/gearComponentType'
import {
  useDeleteGearComponentMutation,
  useGearComponentsQuery,
  useGearComponentTypesQuery,
} from '@/features/gears/composables/useGearComponents'
import { useI18n } from 'vue-i18n'

/**
 * The components section of the gear detail page: the parts list with the
 * show-inactive filter plus the full add/edit/delete flow. Self-contained — it
 * owns its queries, the component form dialog, and the delete confirmation, so
 * the detail view only has to place it in the layout. Renders the `ListPanel`
 * alongside two teleported dialogs, so `inheritAttrs` is disabled and the
 * layout class is forwarded to the panel via `$attrs`.
 */
defineOptions({ inheritAttrs: false })

const props = defineProps<{
  /** The parent gear whose components are managed here. */
  gear: Gear
  /** The viewer's measurement system, passed to list items and the form. */
  units: Schemas['Units']
  /** The viewer's currency, passed to list items and the form. */
  currency: Schemas['Currency']
}>()

const { t } = useI18n()
const toasts = useToasts()

const gearId = computed(() => props.gear.id)

const componentsQuery = useGearComponentsQuery(gearId)
const componentTypesQuery = useGearComponentTypesQuery()
const components = computed(() => componentsQuery.data.value ?? [])
const supportsComponents = computed(() => gearTypeSupportsComponents(props.gear.gearType))
// Inactive components are hidden by default, matching v1; the filter reveals them.
const showInactiveComponents = ref(false)
const isComponentFilterOpen = ref(false)
const visibleComponents = computed(() =>
  showInactiveComponents.value
    ? components.value
    : components.value.filter((component) => component.active),
)
/** Number of active filters, surfaced as a badge on the Filters trigger. */
const activeComponentFilterCount = computed(() => (showInactiveComponents.value ? 1 : 0))
// The type catalogue valid for this gear family, fed to the form's select.
const availableComponentTypes = computed<string[]>(() => {
  const key = componentTypeListKey(props.gear.gearType)
  const lists = componentTypesQuery.data.value
  return key && lists ? lists[key] : []
})

// Component add/edit dialog state. `editingComponent` null means "add".
const isComponentFormOpen = ref(false)
const editingComponent = ref<GearComponent | null>(null)

function openAddComponent(): void {
  editingComponent.value = null
  isComponentFormOpen.value = true
}

function openEditComponent(component: GearComponent): void {
  editingComponent.value = component
  isComponentFormOpen.value = true
}

// Component delete dialog state.
const isComponentDeleteOpen = ref(false)
const componentToDelete = ref<GearComponent | null>(null)
const deleteComponentMutation = useDeleteGearComponentMutation()

/** Display name (brand + model) for the component queued for deletion. */
const componentToDeleteName = computed(() =>
  componentToDelete.value
    ? `${componentToDelete.value.brand} ${componentToDelete.value.model}`.trim()
    : '',
)

function openDeleteComponent(component: GearComponent): void {
  componentToDelete.value = component
  isComponentDeleteOpen.value = true
}

function confirmDeleteComponent(): void {
  const component = componentToDelete.value
  if (!component) {
    return
  }
  deleteComponentMutation.mutate(
    { id: component.id, version: component.version },
    {
      onSuccess: () => {
        isComponentDeleteOpen.value = false
        toasts.success(t('gears.components.delete.success'))
      },
      onError: () => {
        toasts.error(t('gears.components.delete.error'))
      },
    },
  )
}

function onFormSuccess(message: string): void {
  toasts.success(message)
}

function onFormError(message: string): void {
  toasts.error(message)
}
</script>

<template>
  <ListPanel
    v-bind="$attrs"
    :is-loading="componentsQuery.isPending.value"
    :is-error="componentsQuery.isError.value"
    :is-empty="components.length === 0"
    :error-title="t('gears.components.error.title')"
    :error-description="t('gears.components.error.description')"
    :retry-label="t('gears.error.retry')"
    @retry="() => componentsQuery.refetch()"
  >
    <template #header>
      <div class="flex items-center justify-between gap-2 px-4 py-3">
        <h2 class="text-card-heading">{{ t('gears.components.title') }}</h2>
        <Popover v-if="components.length > 0" v-model:open="isComponentFilterOpen">
          <PopoverTrigger as-child>
            <Button variant="outline" size="sm">
              <Filter class="size-4" aria-hidden="true" />
              {{ t('gears.filters') }}
              <CountBadge :count="activeComponentFilterCount" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" class="w-56">
            <Switch v-model="showInactiveComponents" class="w-full">
              {{ t('gears.showInactive') }}
            </Switch>
          </PopoverContent>
        </Popover>
      </div>
    </template>

    <template #loading>
      <div class="divide-y divide-border" aria-busy="true">
        <div v-for="n in 3" :key="n" class="space-y-2 px-4 py-3">
          <Skeleton class="h-4 w-1/3" />
          <Skeleton class="h-3 w-1/5" />
          <Skeleton class="h-1.5 w-full" />
        </div>
      </div>
    </template>

    <template #empty>
      <p class="px-4 py-8 text-center text-hint">
        {{ supportsComponents ? t('gears.components.empty') : t('gears.components.unsupported') }}
      </p>
    </template>

    <!-- Ready: the list, or a notice when the active filter hides them all. -->
    <p v-if="visibleComponents.length === 0" class="px-4 py-8 text-center text-hint">
      {{ t('gears.components.noneActive') }}
    </p>
    <ul v-else class="divide-y divide-border">
      <li v-for="component in visibleComponents" :key="component.id">
        <GearComponentListItem
          :component="component"
          :gear-type="gear.gearType"
          :units="units"
          :currency="currency"
          @edit="openEditComponent"
          @delete="openDeleteComponent"
        />
      </li>
    </ul>

    <template #footer>
      <div v-if="supportsComponents" class="p-3">
        <Button variant="outline" size="sm" class="w-full" @click="openAddComponent">
          <Plus class="size-4" aria-hidden="true" />
          {{ t('gears.components.add') }}
        </Button>
      </div>
    </template>
  </ListPanel>

  <GearComponentFormDialog
    v-model:open="isComponentFormOpen"
    :component="editingComponent"
    :gear-id="gear.id"
    :gear-type="gear.gearType"
    :available-types="availableComponentTypes"
    :units="units"
    :currency="currency"
    @success="onFormSuccess"
    @error="onFormError"
  />
  <ConfirmDialog
    v-model:open="isComponentDeleteOpen"
    :title="t('gears.components.delete.title')"
    :description="t('gears.components.delete.body', { name: componentToDeleteName })"
    :confirm-label="t('gears.components.delete.confirm')"
    :cancel-label="t('gears.components.delete.cancel')"
    :close-label="t('gears.components.delete.close')"
    :pending="deleteComponentMutation.isPending.value"
    @confirm="confirmDeleteComponent"
  />
</template>
