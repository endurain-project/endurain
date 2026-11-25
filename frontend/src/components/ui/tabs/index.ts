export { default as Tabs } from './Tabs.vue'
export { default as TabsContent } from './TabsContent.vue'
export { default as TabsList } from './TabsList.vue'
export { default as TabsTrigger } from './TabsTrigger.vue'

/** The look of a tab list, shared with a navigation drawn as tabs. */
export const tabsListClass =
  'inline-flex items-center gap-1 rounded-input border border-border bg-background p-1'

/** The look of a tab, without its active state, shared with a navigation link drawn as a tab. */
export const tabsTriggerClass =
  'inline-flex cursor-pointer items-center justify-center rounded-input px-3 py-1.5 text-item-title text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/30'
