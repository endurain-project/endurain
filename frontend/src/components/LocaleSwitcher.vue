<script setup lang="ts">
import { Select } from '@/components/ui/select'
import { isSupportedLocale } from '@/i18n'
import { useLocale } from '@/composables/useLocale'

const { t, locale, availableLocales, setLocale } = useLocale()

async function onChange(value: string): Promise<void> {
  if (isSupportedLocale(value)) {
    await setLocale(value)
  }
}
</script>

<template>
  <div class="flex items-center gap-2">
    <label class="sr-only" for="locale-select">{{ t('app.language') }}</label>
    <!-- h-8 matches the icon-sm ThemeToggle it sits beside. -->
    <Select id="locale-select" :model-value="locale" class="h-8" @update:model-value="onChange">
      <option v-for="option in availableLocales" :key="option.code" :value="option.code">
        {{ option.label }}
      </option>
    </Select>
  </div>
</template>
