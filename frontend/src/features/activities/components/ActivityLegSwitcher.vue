<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { LayoutList } from '@lucide/vue'

import type { ActivitySummary } from '@/features/activities/types'

import { tabsListClass, tabsTriggerClass } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { presentActivityType } from '@/features/activities/utils/activityType'
import { labelLegs } from '@/features/activities/utils/legs'

const props = defineProps<{
  /** The multisport activity the legs belong to. */
  parentId: string
  /** The legs, in leg order. */
  legs: ActivitySummary[]
  /** The activity on show: the multisport activity (Overview) or one of its legs. */
  activeId: string
}>()

const { t } = useI18n()

/** Overview first, then one link per leg, labelled by sport with transitions numbered. */
const links = computed(() => [
  { id: props.parentId, icon: LayoutList, label: t('activities.multisport.overview') },
  ...labelLegs(props.legs, (type) => presentActivityType(type).labelKey).map(
    ({ leg, labelKey, number }) => ({
      id: leg.id,
      icon: presentActivityType(leg.activityType).icon,
      label:
        number === null
          ? t(labelKey)
          : t('activities.multisport.numberedLeg', { label: t(labelKey), number }),
    }),
  ),
])

/** A link drawn as a tab; the page on show is the active one. */
const linkClass = cn(
  tabsTriggerClass,
  'gap-1.5 whitespace-nowrap aria-[current=page]:bg-card aria-[current=page]:text-foreground aria-[current=page]:shadow-sm',
)
</script>

<template>
  <nav :aria-label="t('activities.multisport.switcher')">
    <div :class="cn(tabsListClass, 'max-w-full overflow-x-auto')">
      <RouterLink
        v-for="link in links"
        :key="link.id"
        :to="{ name: 'activity', params: { id: link.id } }"
        :aria-current="link.id === activeId ? 'page' : undefined"
        :class="linkClass"
      >
        <component :is="link.icon" class="size-4" aria-hidden="true" />
        {{ link.label }}
      </RouterLink>
    </div>
  </nav>
</template>
