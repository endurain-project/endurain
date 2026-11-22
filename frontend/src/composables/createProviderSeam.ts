/**
 * Shared registration mechanic for the deployment provider seams (telemetry,
 * map, chart, image source). Each seam is a module-level
 * singleton that holds a default implementation until hosted/SaaS bootstrap
 * replaces it once. This factory captures that mechanic — default value,
 * one-time registration, current-value access, and a registered flag — so each
 * seam only declares its own contract and public hook on top.
 */

/**
 * Registration handle for a single provider seam.
 *
 * @typeParam T - The provider/adapter/resolver type the seam stores.
 */
export interface ProviderSeam<T> {
  /**
   * Replaces the active implementation. Call once during bootstrap on
   * deployments that ship a concrete implementation.
   *
   * @param next - The implementation to install.
   */
  set(next: T): void
  /**
   * Returns the current implementation — the default until {@link set} runs.
   * Read on each access so consumers always observe the latest registration.
   *
   * @returns The active implementation.
   */
  get(): T
  /**
   * Reports whether a concrete implementation has been registered.
   *
   * @returns `true` once {@link set} has been called, otherwise `false`.
   */
  isRegistered(): boolean
}

/**
 * Creates a provider seam holding `defaultValue` until a concrete
 * implementation is registered.
 *
 * @typeParam T - The provider/adapter/resolver type the seam stores.
 * @param defaultValue - The default used until {@link ProviderSeam.set} runs.
 * @returns The seam's `set`, `get`, and `isRegistered` accessors.
 */
export function createProviderSeam<T>(defaultValue: T): ProviderSeam<T> {
  let current: T = defaultValue
  let registered = false

  return {
    set(next: T): void {
      current = next
      registered = true
    },
    get(): T {
      return current
    },
    isRegistered(): boolean {
      return registered
    },
  }
}
