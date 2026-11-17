import { readonly, ref, toValue, watch, type MaybeRefOrGetter, type Ref } from 'vue'

/**
 * A reactive clock: the current epoch milliseconds, refreshed on an interval.
 * Pass `null` as the interval to pause it (no timer runs); the timer is cleared
 * when the interval changes or the owning scope is disposed.
 *
 * @param intervalMs - Refresh period in milliseconds, or `null` to pause.
 * @returns A read-only ref of the current epoch milliseconds.
 */
export function useNow(intervalMs: MaybeRefOrGetter<number | null>): Readonly<Ref<number>> {
  const now = ref(Date.now())

  watch(
    () => toValue(intervalMs),
    (ms, _previous, onCleanup) => {
      now.value = Date.now()
      if (ms === null) {
        return
      }
      const timer = setInterval(() => {
        now.value = Date.now()
      }, ms)
      onCleanup(() => clearInterval(timer))
    },
    { immediate: true },
  )

  return readonly(now)
}
