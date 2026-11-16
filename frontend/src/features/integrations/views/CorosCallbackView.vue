<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import { LoaderCircle } from '@lucide/vue'

import { useToasts } from '@/composables/useToasts'
import { queryKeys } from '@/services/queryKeys'
import { completeCorosLink } from '@/features/integrations/services/coros'

/**
 * Handles the COROS OAuth redirect. COROS sends the browser back with `state`
 * and `code`; the backend validates the state against the caller and stores the
 * tokens, then the profile is refreshed so the integrations card flips to
 * connected.
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const toasts = useToasts()
const client = useQueryClient()

onMounted(async () => {
  const state = typeof route.query.state === 'string' ? route.query.state : ''
  const code = typeof route.query.code === 'string' ? route.query.code : ''

  if (!state || !code) {
    toasts.error(t('settings.integrations.coros.connectError'))
    await router.replace({ name: 'settings-integrations' })
    return
  }

  try {
    await completeCorosLink(code, state)
    await client.invalidateQueries({ queryKey: queryKeys.profile.all() })
    await client.invalidateQueries({ queryKey: queryKeys.integrations.corosStatus() })
    toasts.success(t('settings.integrations.coros.linkSuccess'))
  } catch {
    toasts.error(t('settings.integrations.coros.connectError'))
  } finally {
    await router.replace({ name: 'settings-integrations' })
  }
})
</script>

<template>
  <div class="flex min-h-[50vh] flex-col items-center justify-center gap-3">
    <LoaderCircle class="size-8 animate-spin text-muted-foreground" aria-hidden="true" />
    <p class="text-body">{{ t('settings.integrations.coros.completing') }}</p>
  </div>
</template>
