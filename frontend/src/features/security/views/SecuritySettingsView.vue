<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import ChangeEmailCard from '@/features/security/components/ChangeEmailCard.vue'
import ChangePasswordCard from '@/features/security/components/ChangePasswordCard.vue'
import LinkedAccountsCard from '@/features/security/components/LinkedAccountsCard.vue'
import MfaCard from '@/features/security/components/MfaCard.vue'
import SessionsCard from '@/features/security/components/SessionsCard.vue'
import ApiKeysCard from '@/features/security/components/ApiKeysCard.vue'
import DeleteAccountCard from '@/features/security/components/DeleteAccountCard.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { useProfileQuery } from '@/features/profile/composables/useProfile'
import { useToasts } from '@/composables/useToasts'
import { consumeIdpStepUpReturn } from '@/features/security/composables/useIdpStepUp'
import { useMfaStatusQuery } from '@/features/security/composables/useSecurity'

const { t } = useI18n()
const toasts = useToasts()

// Returning from an identity-provider sign-in, the callback leaves its outcome
// in the URL fragment. It is consumed once; the card that started it reopens its
// dialog with the resume, and a failure is reported once the page is shown.
const stepUpReturn = consumeIdpStepUpReturn()
const resume = stepUpReturn && !stepUpReturn.error ? stepUpReturn : null
onMounted(() => {
  if (stepUpReturn?.error === 'not_fresh') {
    toasts.error(t('settings.security.stepUp.notFresh'))
  } else if (stepUpReturn?.error) {
    toasts.error(t('settings.security.stepUp.failed'))
  }
})

// The profile carries `hasLocalPassword`, which gates the change-password card
// and the step-up password fields. MFA status (shared cache key with MfaCard)
// drives whether the change-password form asks for an MFA code.
const profileQuery = useProfileQuery()
const profile = computed(() => profileQuery.data.value ?? null)
const mfaStatusQuery = useMfaStatusQuery()
const mfaEnabled = computed(() => mfaStatusQuery.data.value?.enabled ?? false)
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('settings.security.title') }}</h1>
      <p class="text-body">{{ t('settings.security.subtitle') }}</p>
    </div>

    <!-- Loading: mirror the stacked cards — form-style (change password, MFA)
         then list-style (linked accounts, sessions) — to match the load. -->
    <div v-if="profileQuery.isPending.value" class="flex flex-col gap-3" aria-busy="true">
      <Card v-for="n in 2" :key="`form-${n}`" class="flex flex-col gap-3">
        <Skeleton class="h-5 w-40" />
        <Skeleton class="h-3 w-64" />
        <Skeleton class="h-9 w-full" />
        <Skeleton class="h-9 w-32" />
      </Card>
      <Card
        v-for="n in 2"
        :key="`list-${n}`"
        padding="none"
        class="divide-y divide-border overflow-hidden"
      >
        <div class="px-4 py-3">
          <Skeleton class="h-5 w-40" />
        </div>
        <div class="divide-y divide-border">
          <div
            v-for="row in 2"
            :key="row"
            class="flex items-center justify-between gap-3 px-4 py-3"
          >
            <div class="space-y-2">
              <Skeleton class="h-4 w-32" />
              <Skeleton class="h-3 w-24" />
            </div>
            <Skeleton class="h-8 w-20" />
          </div>
        </div>
      </Card>
    </div>

    <!-- Error -->
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

    <!-- Loaded -->
    <template v-else-if="profile">
      <ChangeEmailCard
        :email="profile.email"
        :has-local-password="profile.hasLocalPassword"
        :mfa-enabled="mfaEnabled"
        :resume="resume"
      />
      <ChangePasswordCard
        v-if="profile.hasLocalPassword"
        :mfa-enabled="mfaEnabled"
        :access-type="profile.accessType"
      />
      <MfaCard :has-local-password="profile.hasLocalPassword" :resume="resume" />
      <LinkedAccountsCard
        :has-local-password="profile.hasLocalPassword"
        :mfa-enabled="mfaEnabled"
        :resume="resume"
      />
      <SessionsCard />
      <ApiKeysCard
        :has-local-password="profile.hasLocalPassword"
        :mfa-enabled="mfaEnabled"
        :resume="resume"
      />
      <DeleteAccountCard
        :username="profile.username"
        :has-local-password="profile.hasLocalPassword"
        :mfa-enabled="mfaEnabled"
        :resume="resume"
      />
    </template>
  </div>
</template>
