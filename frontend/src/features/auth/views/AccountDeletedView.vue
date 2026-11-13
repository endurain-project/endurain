<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'

import AppLogo from '@/components/AppLogo.vue'
import { Button } from '@/components/ui/button'

const { t } = useI18n()
</script>

<template>
  <section class="mx-auto w-full max-w-md">
    <div class="rounded-card border border-border bg-card p-6 sm:p-8">
      <AppLogo width="40" height="40" class="mx-auto mb-3 size-10" />

      <div class="flex flex-col items-center text-center">
        <h1 class="text-card-heading">{{ t('login.accountDeleted.title') }}</h1>
        <p class="mt-2 text-body">{{ t('login.accountDeleted.body') }}</p>
        <Button as-child class="mt-6">
          <RouterLink :to="{ name: 'login' }">{{
            t('login.accountDeleted.backToLogin')
          }}</RouterLink>
        </Button>
      </div>
    </div>
  </section>
</template>
