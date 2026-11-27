<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'

import AppLogo from '@/components/AppLogo.vue'
import MfaCard from '@/features/security/components/MfaCard.vue'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import { useSignOut } from '@/features/auth/composables/useSignOut'
import { useAuthStore } from '@/features/auth/stores/auth'
import { useProfileQuery } from '@/features/profile/composables/useProfile'
import { consumeIdpStepUpReturn } from '@/features/security/composables/useIdpStepUp'
import { useMfaStatusQuery } from '@/features/security/composables/useSecurity'

const { t } = useI18n()
const router = useRouter()
const toasts = useToasts()
const auth = useAuthStore()
const queryClient = useQueryClient()
const { signOut } = useSignOut()

// An account without a local password proves itself again through its identity provider, which returns here
// with the outcome in the URL fragment; the MFA card reopens its dialog with it.
const stepUpReturn = consumeIdpStepUpReturn()
const resume = stepUpReturn && !stepUpReturn.error ? stepUpReturn : null
onMounted(() => {
  if (stepUpReturn?.error === 'not_fresh') {
    toasts.error(t('settings.security.stepUp.notFresh'))
  } else if (stepUpReturn?.error) {
    toasts.error(t('settings.security.stepUp.failed'))
  }
})

const profileQuery = useProfileQuery()
const profile = computed(() => profileQuery.data.value ?? null)

// The server accepts the account again as soon as MFA is set up. The page stays until the user continues, so
// the backup codes the card shows are not lost.
const statusQuery = useMfaStatusQuery()
const enrolled = computed(() => statusQuery.data.value?.enabled === true)
watch(
  enrolled,
  (isEnrolled) => {
    if (isEnrolled) {
      auth.completeMfaEnrolment()
    }
  },
  { immediate: true },
)

/** Asks again what the server refused until now, then opens the app. */
async function continueToApp(): Promise<void> {
  await queryClient.invalidateQueries()
  await router.push({ name: 'home' })
}
</script>

<template>
  <section class="mx-auto flex w-full max-w-xl flex-col gap-3">
    <div class="flex flex-col items-center gap-2 text-center">
      <AppLogo width="40" height="40" class="size-10" />
      <h1 class="text-page-title">{{ t('settings.security.mfaEnrolment.title') }}</h1>
      <p class="text-body">{{ t('settings.security.mfaEnrolment.description') }}</p>
    </div>

    <div v-if="profileQuery.isPending.value" class="flex flex-col gap-2" aria-busy="true">
      <Skeleton class="h-5 w-48" />
      <Skeleton class="h-9 w-36" />
    </div>

    <ErrorState
      v-else-if="profileQuery.isError.value"
      :title="t('settings.security.loadError.title')"
      :description="t('settings.security.loadError.description')"
    >
      <template #action>
        <Button variant="outline" @click="() => profileQuery.refetch()">
          {{ t('settings.security.retry') }}
        </Button>
      </template>
    </ErrorState>

    <MfaCard v-else-if="profile" :has-local-password="profile.hasLocalPassword" :resume="resume" />

    <Alert v-if="enrolled" kind="success">
      {{ t('settings.security.mfaEnrolment.done') }}
    </Alert>

    <div class="flex flex-wrap justify-center gap-2">
      <Button v-if="enrolled" data-test="continue" @click="continueToApp">
        {{ t('settings.security.mfaEnrolment.continue') }}
      </Button>
      <Button variant="outline" data-test="sign-out" @click="signOut">
        {{ t('settings.security.mfaEnrolment.signOut') }}
      </Button>
    </div>
  </section>
</template>
