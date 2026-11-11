import type { StepUpAction } from '@/features/security/types'

/** The tabs of the profile page, in display order. */
export const PROFILE_TABS = ['profile', 'privacy'] as const

/** One tab of the profile page. */
export type ProfileTab = (typeof PROFILE_TABS)[number]

/** The tab shown when the URL names none, or an unknown one. */
export const DEFAULT_PROFILE_TAB: ProfileTab = 'profile'

/**
 * The tab whose card started a step-up. The identity-provider callback returns to the page without its
 * `?tab=`, so the page opens this tab to show the card that reopens its dialog.
 *
 * @param action - The operation the step-up authorised.
 * @returns The tab that holds the card, or the default tab for an action the page does not own.
 */
export function profileTabForAction(action: StepUpAction): ProfileTab {
  return action === 'profile_export' ? 'privacy' : DEFAULT_PROFILE_TAB
}
