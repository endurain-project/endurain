import { computed, toValue, type ComputedRef, type MaybeRefOrGetter } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getScalarQueryString } from '@/composables/useRouteQuery'

/** The active tab of a page, kept in the `?tab=` query so it can be linked and survives a reload. */
export interface TabQuery<T extends string> {
  /** The tab named by the URL, or the fallback when it names none of the page's tabs. */
  activeTab: ComputedRef<T>
  /** Switches tab by replacing the URL, keeping every other query param. */
  selectTab: (value: string | number) => Promise<void>
}

/**
 * Binds a page's tabs to the `?tab=` query.
 *
 * @param tabs - The tabs the page offers, in display order.
 * @param fallback - The tab shown when the URL names none, or an unknown one.
 * @returns The active tab and a function that switches to another.
 */
export function useTabQuery<T extends string>(
  tabs: MaybeRefOrGetter<readonly T[]>,
  fallback: T,
): TabQuery<T> {
  const route = useRoute()
  const router = useRouter()

  /**
   * Narrows a raw value to one of the page's tabs.
   *
   * @param value - The raw value.
   * @returns The tab, or the fallback.
   */
  function parse(value: unknown): T {
    return toValue(tabs).find((tab) => tab === value) ?? fallback
  }

  const activeTab = computed(() => parse(getScalarQueryString(route.query.tab)))

  async function selectTab(value: string | number): Promise<void> {
    await router.replace({ query: { ...route.query, tab: parse(value) } })
  }

  return { activeTab, selectTab }
}
