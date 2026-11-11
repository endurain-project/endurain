<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { ApiKey } from '@/features/security/types'

import { Badge } from '@/components/ui/badge'
import { formatMediumDate } from '@/utils/datetime'

/**
 * What an API key row shows: its name, prefix, active or revoked state, granted scopes and
 * created, last-used and expiry dates. Shared by the user's own API keys card and the admin
 * view of another user's keys; the row's actions stay with the card.
 */
defineProps<{
  /** The key to describe. */
  apiKey: ApiKey
}>()

const { t, locale } = useI18n()

/** Formats an ISO date in the active locale, or `''` when unparseable. */
function formatDate(iso: string): string {
  return formatMediumDate(iso, locale.value)
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-1.5">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-body font-medium">{{ apiKey.name }}</span>
      <code class="rounded bg-muted-foreground/15 px-1.5 py-0.5 font-mono text-xs">
        {{ apiKey.keyPrefix }}…
      </code>
      <Badge :variant="apiKey.isActive ? 'secondary' : 'destructive'">
        {{
          apiKey.isActive
            ? t('settings.security.apiKeys.statusActive')
            : t('settings.security.apiKeys.statusRevoked')
        }}
      </Badge>
    </div>
    <div v-if="apiKey.scopes.length > 0" class="flex flex-wrap gap-1">
      <Badge v-for="scope in apiKey.scopes" :key="scope" variant="outline" class="font-mono">
        {{ scope }}
      </Badge>
    </div>
    <p class="text-hint">
      {{ t('settings.security.apiKeys.created', { date: formatDate(apiKey.createdAt) }) }} ·
      {{
        apiKey.lastUsedAt
          ? t('settings.security.apiKeys.lastUsed', { date: formatDate(apiKey.lastUsedAt) })
          : t('settings.security.apiKeys.neverUsed')
      }}
      ·
      {{ t('settings.security.apiKeys.expires', { date: formatDate(apiKey.expiresAt) }) }}
    </p>
  </div>
</template>
