import { ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

import type { ZxcvbnFactory } from '@zxcvbn-ts/core'

/** A zxcvbn score: 0 (too guessable) to 4 (very unguessable). */
export type PasswordScore = 0 | 1 | 2 | 3 | 4

let scorer: Promise<ZxcvbnFactory> | null = null

/**
 * Loads zxcvbn and its dictionaries on first use, so they ship in their own
 * chunk instead of the main bundle, and configures the scorer once.
 *
 * @returns The configured scorer.
 * @throws {Error} When a chunk cannot be fetched; the next call retries.
 */
function loadScorer(): Promise<ZxcvbnFactory> {
  scorer ??= import('@/features/security/utils/passwordScorer')
    .then((module) => module.createPasswordScorer())
    .catch((error: unknown) => {
      scorer = null
      throw error
    })
  return scorer
}

/**
 * Scores a password for the advisory strength meter. The score never gates a
 * form: the server decides whether a password is accepted.
 *
 * @param password - The password being typed.
 * @param userInputs - Account details (username, email, name) the password
 *   should not be built from; blanks are ignored.
 * @returns `score`, `null` while the password is empty, not yet scored or the
 *   scorer could not be loaded.
 */
export function usePasswordStrength(
  password: MaybeRefOrGetter<string>,
  userInputs: MaybeRefOrGetter<readonly string[]>,
) {
  const score = ref<PasswordScore | null>(null)
  let latest = 0

  watch(
    [() => toValue(password), () => toValue(userInputs)],
    async ([value, inputs]) => {
      const run = ++latest
      if (value.length === 0) {
        score.value = null
        return
      }
      try {
        const result = (await loadScorer()).check(
          value,
          inputs.filter((input) => input.length > 0),
        )
        if (run === latest) {
          score.value = result.score
        }
      } catch {
        // The meter is advisory; without the scorer it simply stays hidden.
        if (run === latest) {
          score.value = null
        }
      }
    },
    { immediate: true },
  )

  return { score }
}
