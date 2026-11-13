<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { cn } from '@/lib/utils'
import {
  usePasswordStrength,
  type PasswordScore,
} from '@/features/security/composables/usePasswordStrength'

const props = withDefaults(
  defineProps<{
    /** The password being typed; the meter is hidden while it is empty. */
    password: string
    /** Account details (username, email, name) the password should not be built from. */
    userInputs?: readonly string[]
  }>(),
  { userInputs: () => [] },
)

const SEGMENTS = 4

/** Fill color per score; the lowest scores read as a warning. */
const SCORE_COLORS: Record<PasswordScore, string> = {
  0: 'bg-destructive',
  1: 'bg-destructive',
  2: 'bg-effort',
  3: 'bg-goal',
  4: 'bg-goal',
}

const { t } = useI18n()
const { score } = usePasswordStrength(
  () => props.password,
  () => props.userInputs,
)

const filled = computed(() => Math.max(score.value ?? 0, 1))
const label = computed(() => {
  switch (score.value) {
    case 0:
      return t('app.password.strength.tooWeak')
    case 1:
      return t('app.password.strength.weak')
    case 2:
      return t('app.password.strength.fair')
    case 3:
      return t('app.password.strength.good')
    case 4:
      return t('app.password.strength.strong')
    default:
      return null
  }
})
</script>

<template>
  <div aria-live="polite">
    <div v-if="score !== null && label" class="flex flex-col gap-1.5" data-strength-bar>
      <div class="flex gap-1" aria-hidden="true">
        <span
          v-for="segment in SEGMENTS"
          :key="segment"
          :data-strength-segment="segment <= filled ? 'filled' : 'empty'"
          :class="
            cn('h-1 flex-1 rounded-badge', segment <= filled ? SCORE_COLORS[score] : 'bg-muted')
          "
        />
      </div>
      <p class="text-hint">{{ t('app.password.strength.label', { level: label }) }}</p>
    </div>
  </div>
</template>
