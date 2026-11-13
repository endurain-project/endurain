<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import ChangeEmailCard from '@/features/security/components/ChangeEmailCard.vue'
import ChangeUsernameCard from '@/features/security/components/ChangeUsernameCard.vue'
import ChangePasswordCard from '@/features/security/components/ChangePasswordCard.vue'
import KnownDevicesCard from '@/features/security/components/KnownDevicesCard.vue'
import LinkedAccountsCard from '@/features/security/components/LinkedAccountsCard.vue'
import MfaCard from '@/features/security/components/MfaCard.vue'
import SessionsCard from '@/features/security/components/SessionsCard.vue'
import ApiKeysCard from '@/features/security/components/ApiKeysCard.vue'
import DeleteAccountCard from '@/features/security/components/DeleteAccountCard.vue'
import SectionTabsBar from '@/components/SectionTabsBar.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent } from '@/components/ui/tabs'
import { useProfileQuery } from '@/features/profile/composables/useProfile'
import { useTabQuery } from '@/composables/useTabQuery'
import { useToasts } from '@/composables/useToasts'
import { consumeIdpStepUpReturn } from '@/features/security/composables/useIdpStepUp'
import { DEFAULT_SECURITY_TAB, SECURITY_TABS, securityTabForAction } from '@/features/security/tabs'

const { t } = useI18n()
const toasts = useToasts()
const { activeTab, selectTab } = useTabQuery(SECURITY_TABS, DEFAULT_SECURITY_TAB)
const tabs = computed(() =>
  SECURITY_TABS.map((tab) => ({ value: tab, label: t(`settings.security.tabs.${tab}`) })),
)

// Returning from an identity-provider sign-in, the callback leaves its outcome
// in the URL fragment. It is consumed once; the card that started it reopens its
// dialog with the resume (on the tab that holds it), and a failure is reported once the page is shown.
const stepUpReturn = consumeIdpStepUpReturn()
const resume = stepUpReturn && !stepUpReturn.error ? stepUpReturn : null
onMounted(() => {
  if (resume) {
    void selectTab(securityTabForAction(resume.action))
  }
  if (stepUpReturn?.error === 'not_fresh') {
    toasts.error(t('settings.security.stepUp.notFresh'))
  } else if (stepUpReturn?.error) {
    toasts.error(t('settings.security.stepUp.failed'))
  }
})

// The profile carries `hasLocalPassword`, which gates the change-password card
// and the step-up password fields, and `mfaEnabled`, which decides whether the
// step-up forms ask for an MFA code.
const profileQuery = useProfileQuery()
const profile = computed(() => profileQuery.data.value ?? null)
const mfaEnabled = computed(() => profile.value?.mfaEnabled ?? false)
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
    <Tabs
      v-else-if="profile"
      class="flex flex-col gap-3"
      :model-value="activeTab"
      @update:model-value="selectTab"
    >
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center">
        <SectionTabsBar
          :model-value="activeTab"
          :tabs="tabs"
          :label="t('settings.security.tabs.label')"
          @update:model-value="selectTab"
        />
      </div>

      <TabsContent value="account" class="mt-0 flex flex-col gap-3">
        <ChangeEmailCard
          :email="profile.email"
          :pending-email="profile.pendingEmail"
          :pending-email-expires-at="profile.pendingEmailExpiresAt"
          :has-local-password="profile.hasLocalPassword"
          :mfa-enabled="mfaEnabled"
          :resume="resume"
        />
        <ChangeUsernameCard
          :username="profile.username"
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
      </TabsContent>
      <TabsContent value="sessions" class="mt-0 flex flex-col gap-3">
        <SessionsCard />
        <KnownDevicesCard
          :has-local-password="profile.hasLocalPassword"
          :mfa-enabled="mfaEnabled"
          :resume="resume"
        />
        <ApiKeysCard
          :has-local-password="profile.hasLocalPassword"
          :mfa-enabled="mfaEnabled"
          :resume="resume"
        />
      </TabsContent>
      <TabsContent value="danger" class="mt-0 flex flex-col gap-3">
        <DeleteAccountCard
          :username="profile.username"
          :has-local-password="profile.hasLocalPassword"
          :mfa-enabled="mfaEnabled"
          :resume="resume"
        />
      </TabsContent>
    </Tabs>
  </div>
</template>
