<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import { LoaderCircle } from '@lucide/vue'

import { useToasts } from '@/composables/useToasts'
import { queryKeys } from '@/services/queryKeys'
import { HttpError } from '@/services/http'
import {
  completeStravaLink,
  STRAVA_SCOPE_INSUFFICIENT_TYPE,
} from '@/features/integrations/services/strava'

/**
 * Handles the Strava OAuth redirect. Strava sends the browser back here with
 * `state` + `code` + `scope`; we exchange them server-side, refresh the profile so the
 * integrations zone reflects the new link, then return to the settings page.
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const toasts = useToasts()
const client = useQueryClient()

onMounted(async () => {
  const state = typeof route.query.state === 'string' ? route.query.state : ''
  const code = typeof route.query.code === 'string' ? route.query.code : ''
  const scope = typeof route.query.scope === 'string' ? route.query.scope : ''

  if (!state || !code || !scope) {
    toasts.error(t('settings.integrations.strava.connectError'))
    await router.replace({ name: 'settings-integrations' })
    return
  }

  try {
    await completeStravaLink(state, code, scope)
    await client.invalidateQueries({ queryKey: queryKeys.profile.all() })
    toasts.success(t('settings.integrations.strava.linkSuccess'))
  } catch (error) {
    const insufficientScope =
      error instanceof HttpError && error.type === STRAVA_SCOPE_INSUFFICIENT_TYPE
    toasts.error(
      t(
        insufficientScope
          ? 'settings.integrations.strava.scopeError'
          : 'settings.integrations.strava.connectError',
      ),
    )
  } finally {
    await router.replace({ name: 'settings-integrations' })
  }
})
</script>

<template>
  <div class="flex min-h-[50vh] flex-col items-center justify-center gap-3">
    <LoaderCircle class="size-8 animate-spin text-muted-foreground" aria-hidden="true" />
    <p class="text-body">{{ t('settings.integrations.strava.completing') }}</p>
  </div>
</template>
