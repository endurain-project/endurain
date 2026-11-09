<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import PrivacySettingsCard from '@/features/profile/components/PrivacySettingsCard.vue'
import ProfileInfoCard from '@/features/profile/components/ProfileInfoCard.vue'
import DefaultGearCard from '@/features/profile/components/DefaultGearCard.vue'
import BlockedUsersCard from '@/features/followers/components/BlockedUsersCard.vue'
import DataTransferCard from '@/features/profile/components/DataTransferCard.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { useProfileQuery } from '@/features/profile/composables/useProfile'
import { useToasts } from '@/composables/useToasts'
import { consumeIdpStepUpReturn } from '@/features/security/composables/useIdpStepUp'

const { t } = useI18n()
const toasts = useToasts()

// Returning from an identity-provider sign-in, the callback leaves its outcome in the URL fragment. It is
// consumed once; the data-transfer card reopens its dialog with the resume, and a failure is reported once the
// page is shown.
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
const mfaEnabled = computed(() => profile.value?.mfaEnabled ?? false)
</script>

<template>
  <div class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('settings.profile.title') }}</h1>
      <p class="text-body">{{ t('settings.profile.subtitle') }}</p>
    </header>

    <!-- Loading: mirror the stacked cards (profile info + default gear, privacy,
         data transfer) so the placeholder matches the loaded layout. -->
    <div v-if="profileQuery.isPending.value" class="flex flex-col gap-3" aria-busy="true">
      <!-- Profile info: avatar + identity fields. -->
      <Card class="flex flex-col gap-3">
        <div class="flex items-center gap-3">
          <Skeleton class="size-28 shrink-0 rounded-full" />
          <div class="flex-1 space-y-2">
            <Skeleton class="h-5 w-1/3" />
            <Skeleton class="h-4 w-1/4" />
          </div>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Skeleton v-for="n in 4" :key="n" class="h-9 w-full" />
        </div>
      </Card>
      <!-- Default gear, privacy, blocked users, data transfer: titled cards. -->
      <Card v-for="n in 4" :key="n" class="flex flex-col gap-3">
        <Skeleton class="h-5 w-40" />
        <Skeleton class="h-3 w-64" />
        <Skeleton class="h-9 w-full" />
      </Card>
    </div>

    <Card v-else-if="profileQuery.isError.value" padding="none">
      <ErrorState
        :title="t('settings.profile.error.title')"
        :description="t('settings.profile.error.description')"
      >
        <template #action>
          <Button variant="outline" @click="profileQuery.refetch()">
            {{ t('settings.profile.error.retry') }}
          </Button>
        </template>
      </ErrorState>
    </Card>

    <template v-else-if="profile">
      <ProfileInfoCard :profile="profile" />
      <DefaultGearCard />
      <!-- Keyed on the version: a refetch that changes it rebuilds the form, so its If-Match is the one it shows. -->
      <PrivacySettingsCard :key="profile.privacy.version" :privacy="profile.privacy" />
      <BlockedUsersCard />
      <DataTransferCard
        :user-id="profile.id"
        :has-local-password="profile.hasLocalPassword"
        :mfa-enabled="mfaEnabled"
        :resume="resume"
      />
    </template>
  </div>
</template>
