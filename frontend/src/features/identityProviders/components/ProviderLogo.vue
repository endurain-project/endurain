<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { KeyRound } from '@lucide/vue'

import { resolveProviderLogo } from '@/features/identityProviders/utils/providerIcon'

const props = defineProps<{
  /** Builtin icon key or a custom icon URL, or `null`. */
  icon: string | null
  /** Provider name, used as the image alt text. */
  name: string
  /** Provider slug, which addresses an uploaded icon. */
  slug?: string | null
  /** Whether an uploaded image is shown instead of `icon`. */
  iconUploaded?: boolean
  /** The provider version, so a replaced uploaded image is refetched. */
  version?: number
}>()

// A custom icon URL can 404; fall back to a generic key icon when it fails.
const failed = ref(false)
const src = computed(() =>
  resolveProviderLogo(props.icon, {
    slug: props.slug,
    iconUploaded: props.iconUploaded ?? false,
    version: props.version,
  }),
)

// A new source (e.g. a replaced uploaded image) gets another chance to load.
watch(src, () => {
  failed.value = false
})
</script>

<template>
  <div
    class="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-input bg-muted-foreground/15"
  >
    <img
      v-if="src && !failed"
      :src="src"
      :alt="name"
      class="size-full object-contain p-1"
      @error="failed = true"
    />
    <KeyRound v-else class="size-5 text-muted-foreground" aria-hidden="true" />
  </div>
</template>
