<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShieldCheck } from '@lucide/vue'

import type { IdpReauth, StepUpAction } from '@/features/security/types'
import type { StepUpPending } from '@/features/security/composables/useIdpStepUp'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import { HttpError } from '@/services/http'
import { useIdpStepUp } from '@/features/security/composables/useIdpStepUp'
import { useLinkedProvidersQuery } from '@/features/security/composables/useLinkedAccounts'

const reauth = defineModel<IdpReauth | null>('reauth', { default: null })

const props = withDefaults(
  defineProps<{
    /** The sensitive operation the sign-in authorises. */
    action: StepUpAction
    /** What to restore after the provider round-trip; never a secret. */
    pendingContext?: StepUpPending
    /** Whether the surrounding action is in flight. */
    disabled?: boolean
  }>(),
  { pendingContext: () => ({}), disabled: false },
)

const { t } = useI18n()
const toasts = useToasts()
const linkedQuery = useLinkedProvidersQuery()
const { start } = useIdpStepUp()

const starting = ref(false)
const providers = computed(() => linkedQuery.data.value ?? [])

/** Sends the browser to the chosen provider to sign in again. */
async function onContinue(idpId: number): Promise<void> {
  starting.value = true
  try {
    await start(idpId, props.action, props.pendingContext)
  } catch (error) {
    starting.value = false
    toasts.error(
      error instanceof HttpError && error.status === 429
        ? t('settings.security.stepUp.tooManyAttempts')
        : t('settings.security.stepUp.startError'),
    )
  }
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <Alert v-if="reauth" kind="success">
      <span class="flex flex-wrap items-center justify-between gap-2">
        <span class="inline-flex items-center gap-2">
          <ShieldCheck class="size-4 shrink-0" aria-hidden="true" />
          {{ t('settings.security.stepUp.ready') }}
        </span>
        <Button type="button" variant="ghost" size="sm" :disabled="disabled" @click="reauth = null">
          {{ t('settings.security.stepUp.restart') }}
        </Button>
      </span>
    </Alert>

    <template v-else>
      <p class="text-hint">{{ t('settings.security.stepUp.prompt') }}</p>
      <Skeleton v-if="linkedQuery.isPending.value" class="h-9 w-full" aria-busy="true" />
      <p v-else-if="linkedQuery.isError.value" class="text-hint">
        {{ t('settings.security.linked.error') }}
      </p>
      <p v-else-if="providers.length === 0" class="text-hint">
        {{ t('settings.security.stepUp.noProviders') }}
      </p>
      <div v-else class="flex flex-col gap-2">
        <Button
          v-for="provider in providers"
          :key="provider.id"
          type="button"
          variant="outline"
          class="justify-start"
          :disabled="disabled || starting"
          @click="onContinue(provider.idpId)"
        >
          {{
            t('settings.security.stepUp.continueWith', {
              name: provider.name ?? provider.slug ?? `#${provider.idpId}`,
            })
          }}
        </Button>
      </div>
    </template>
  </div>
</template>
