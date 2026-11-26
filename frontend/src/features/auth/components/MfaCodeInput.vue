<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { cn } from '@/lib/utils'

/**
 * Second-factor code field drawn as one box per character: six digits for an authenticator code, or eight letters
 * and digits (`XXXX-XXXX`) for a backup code. One real input sits over the boxes, so typing, pasting, password
 * managers and screen readers all work on a single field.
 */
const props = defineProps<{
  /** Id of the input, which the field's `<Label for>` names. */
  id: string
  /** Whether the field is disabled. */
  disabled?: boolean
}>()

/** The typed code: upper case, without spaces or the dash. */
const model = defineModel<string>({ default: '' })

const { t } = useI18n()

type CodeKind = 'totp' | 'backup'

/** Box indexes per visual group, for each kind of code. */
const SLOT_GROUPS: Record<CodeKind, number[][]> = {
  totp: [
    [0, 1, 2],
    [3, 4, 5],
  ],
  backup: [
    [0, 1, 2, 3],
    [4, 5, 6, 7],
  ],
}

/** Characters each kind of code is made of; everything else is dropped as it is typed. */
const NOT_ALLOWED: Record<CodeKind, RegExp> = { totp: /\D/g, backup: /[^A-Z0-9]/g }

/** A whole backup code, with or without its dash. */
const BACKUP_CODE = /^[A-Z0-9]{4}-?[A-Z0-9]{4}$/

const kind = ref<CodeKind>('totp')
const isFocused = ref(false)
const inputElement = ref<HTMLInputElement | null>(null)

const slotGroups = computed(() => SLOT_GROUPS[kind.value])
const codeLength = computed(() => slotGroups.value.flat().length)
const activeIndex = computed(() => Math.min(model.value.length, codeLength.value - 1))
const hintId = computed(() => `${props.id}-hint`)

/**
 * Keeps only the characters the current kind of code allows, up to its length, and auto-submits a code that
 * became whole. A pasted or autofilled backup code switches the field to backup-code entry.
 *
 * @param event - The input event.
 */
function onInput(event: Event): void {
  const input = event.target as HTMLInputElement
  const typed = input.value.replace(/\s+/g, '').toUpperCase()
  if (kind.value === 'totp' && BACKUP_CODE.test(typed)) {
    kind.value = 'backup'
  }
  const previous = model.value
  const code = typed.replace(NOT_ALLOWED[kind.value], '').slice(0, codeLength.value)
  input.value = code
  model.value = code
  if (code.length === codeLength.value && code !== previous) {
    void submitWhenReady(input)
  }
}

/**
 * Submits the enclosing form as pressing Enter would: only when its submit button is enabled.
 *
 * @param input - The code input.
 */
async function submitWhenReady(input: HTMLInputElement): Promise<void> {
  // The form re-renders its submit button's disabled state from the new code first.
  await nextTick()
  const form = input.form
  const submit = form?.querySelector<HTMLButtonElement>('button[type="submit"]')
  if (form && submit && !submit.disabled) {
    form.requestSubmit(submit)
  }
}

/**
 * Keeps the caret after the last character, the only place the boxes can be edited from.
 *
 * @param event - The focus or click event.
 */
function moveCaretToEnd(event: Event): void {
  const input = event.target as HTMLInputElement
  input.setSelectionRange(input.value.length, input.value.length)
}

/**
 * Marks the field focused and keeps the caret at the end.
 *
 * @param event - The focus event.
 */
function onFocus(event: FocusEvent): void {
  isFocused.value = true
  moveCaretToEnd(event)
}

/**
 * Switches between authenticator-code and backup-code entry, clearing the code.
 */
function toggleKind(): void {
  kind.value = kind.value === 'totp' ? 'backup' : 'totp'
  model.value = ''
  inputElement.value?.focus()
}
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <div class="relative w-full max-w-sm">
      <div class="flex items-center gap-2" aria-hidden="true">
        <template v-for="(group, groupIndex) in slotGroups" :key="groupIndex">
          <span v-if="groupIndex > 0 && kind === 'backup'" class="text-muted-foreground">–</span>
          <div class="flex min-w-0 flex-1 gap-1.5">
            <div
              v-for="index in group"
              :key="index"
              data-slot="mfa-code-box"
              :class="
                cn(
                  'flex h-12 min-w-0 flex-1 items-center justify-center rounded-input border border-input bg-background text-metric font-medium text-foreground transition-colors',
                  isFocused && index === activeIndex && 'border-ring ring-3 ring-ring/20',
                  disabled && 'opacity-50',
                )
              "
            >
              {{ model[index] }}
              <span
                v-if="isFocused && index === activeIndex && !model[index]"
                class="h-5 w-px animate-pulse bg-foreground"
              />
            </div>
          </div>
        </template>
      </div>
      <input
        :id="id"
        ref="inputElement"
        :value="model"
        type="text"
        :inputmode="kind === 'totp' ? 'numeric' : 'text'"
        autocomplete="one-time-code"
        :autocapitalize="kind === 'backup' ? 'characters' : 'off'"
        spellcheck="false"
        :disabled="disabled"
        :aria-describedby="hintId"
        class="absolute inset-0 size-full cursor-text bg-transparent text-base text-transparent caret-transparent outline-none selection:bg-transparent disabled:cursor-not-allowed"
        @input="onInput"
        @focus="onFocus"
        @blur="isFocused = false"
        @click="moveCaretToEnd"
        @keydown.left.right.up.down.home.end.prevent
      />
    </div>
    <p :id="hintId" class="text-hint">
      {{ kind === 'totp' ? t('login.mfaCodeInput.totpHint') : t('login.mfaCodeInput.backupHint') }}
    </p>
    <button
      type="button"
      class="self-start text-meta text-muted-foreground hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
      :disabled="disabled"
      @click="toggleKind"
    >
      {{
        kind === 'totp'
          ? t('login.mfaCodeInput.useBackupCode')
          : t('login.mfaCodeInput.useAuthenticator')
      }}
    </button>
  </div>
</template>
